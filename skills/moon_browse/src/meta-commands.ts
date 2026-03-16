/**
 * Meta commands handler — simplified
 */
import type { BrowserManager } from './browser-manager';
import { handleSnapshot } from './snapshot';

export async function handleMetaCommand(
  command: string,
  args: string[],
  bm: BrowserManager,
  shutdown: () => void
): Promise<string> {
  const page = bm.getPage();

  switch (command) {
    case 'tabs':
      return `Active tabs: 1`;
    case 'status':
      return `Status: healthy\nURL: ${page.url()}`;
    case 'url':
      return page.url();
    case 'stop':
      shutdown();
      return 'Server stopped';
    case 'screenshot': {
      const path = args[0] || '/tmp/screenshot.png';
      await page.screenshot({ path, fullPage: true });
      return `Screenshot saved: ${path}`;
    }
    case 'snapshot':
      return await handleSnapshot(args, bm);
    default:
      return `(meta command not implemented: ${command})`;
  }
}
