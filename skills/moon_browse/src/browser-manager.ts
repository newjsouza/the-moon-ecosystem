/**
 * Browser lifecycle manager — simplified for Moon-Stack
 */

import { chromium, type Browser, type BrowserContext, type Page, type Locator } from 'playwright';

export class BrowserManager {
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private pages: Map<number, Page> = new Map();
  private activeTabId: number = 0;
  private nextTabId: number = 1;
  private refMap: Map<string, Locator> = new Map();
  private lastSnapshot: string | null = null;

  public serverPort: number = 0;

  async launch() {
    this.browser = await chromium.launch({ headless: true });
    
    this.browser.on('disconnected', () => {
      console.error('[browse] FATAL: Chromium process disconnected');
      process.exit(1);
    });

    this.context = await this.browser.newContext({
      viewport: { width: 1280, height: 720 },
    });

    await this.newTab();
  }

  async close() {
    if (this.browser) {
      this.browser.removeAllListeners('disconnected');
      await this.browser.close();
      this.browser = null;
    }
  }

  async isHealthy(): Promise<boolean> {
    if (!this.browser || !this.browser.isConnected()) return false;
    try {
      const page = this.pages.get(this.activeTabId);
      if (!page) return true;
      await Promise.race([
        page.evaluate('1'),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 2000)),
      ]);
      return true;
    } catch {
      return false;
    }
  }

  async newTab(url?: string): Promise<number> {
    if (!this.context) throw new Error('Browser not launched');

    const page = await this.context.newPage();
    const id = this.nextTabId++;
    this.pages.set(id, page);
    this.activeTabId = id;

    if (url) {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
    }

    return id;
  }

  getPage(): Page {
    const page = this.pages.get(this.activeTabId);
    if (!page) throw new Error('No active page. Use "goto" first.');
    return page;
  }

  getCurrentUrl(): string {
    try {
      return this.getPage().url();
    } catch {
      return 'about:blank';
    }
  }

  getTabCount(): number {
    return this.pages.size;
  }

  setRefMap(refs: Map<string, Locator>) {
    this.refMap = refs;
  }

  clearRefs() {
    this.refMap.clear();
  }

  resolveRef(selector: string): { locator: Locator } | { selector: string } {
    if (selector.startsWith('@e') || selector.startsWith('@c')) {
      const ref = selector.slice(1);
      const locator = this.refMap.get(ref);
      if (!locator) {
        throw new Error(`Ref ${selector} not found. Run 'snapshot' to get fresh refs.`);
      }
      return { locator };
    }
    return { selector };
  }

  setLastSnapshot(text: string | null) {
    this.lastSnapshot = text;
  }

  getLastSnapshot(): string | null {
    return this.lastSnapshot;
  }
}
