/**
 * Write commands handler — simplified
 */
import type { BrowserManager } from './browser-manager';

export async function handleWriteCommand(
  command: string,
  args: string[],
  bm: BrowserManager
): Promise<string> {
  const page = bm.getPage();

  switch (command) {
    case 'goto': {
      const url = args[0];
      if (!url) throw new Error('Usage: goto <url>');
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
      return `Navigated to ${url} (${response?.status() || 'unknown'})`;
    }
    case 'click': {
      const selector = args[0];
      if (!selector) throw new Error('Usage: click <selector>');
      await page.click(selector, { timeout: 5000 });
      return `Clicked ${selector}`;
    }
    case 'fill': {
      const [selector, ...valueParts] = args;
      const value = valueParts.join(' ');
      if (!selector || !value) throw new Error('Usage: fill <selector> <value>');
      await page.fill(selector, value, { timeout: 5000 });
      return `Filled ${selector}`;
    }
    case 'press': {
      const key = args[0];
      if (!key) throw new Error('Usage: press <key>');
      await page.keyboard.press(key);
      return `Pressed ${key}`;
    }
    case 'screenshot': {
      const path = args[0] || '/tmp/screenshot.png';
      await page.screenshot({ path, fullPage: true });
      return `Screenshot saved: ${path}`;
    }
    default:
      return `(write command not implemented: ${command})`;
  }
}
