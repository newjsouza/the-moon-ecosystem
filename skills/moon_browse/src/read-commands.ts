/**
 * Read commands handler — simplified
 */
import type { BrowserManager } from './browser-manager';

export async function handleReadCommand(
  command: string,
  args: string[],
  bm: BrowserManager
): Promise<string> {
  const page = bm.getPage();

  switch (command) {
    case 'text':
      return await page.evaluate(() => document.body.innerText);
    case 'html':
      return await page.content();
    case 'links':
      return await page.evaluate(() => 
        [...document.querySelectorAll('a[href]')]
          .map(a => `${a.textContent?.trim()} → ${(a as HTMLAnchorElement).href}`)
          .join('\n')
      );
    case 'console':
      return '(console buffer - use browser console for logs)';
    default:
      return `(read command not implemented: ${command})`;
  }
}
