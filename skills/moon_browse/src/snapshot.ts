/**
 * Snapshot command — simplified for Moon-Stack
 */
import type { BrowserManager } from './browser-manager';

export const SNAPSHOT_FLAGS = [
  { short: '-i', long: '--interactive', description: 'Interactive elements only', optionKey: 'interactive' },
  { short: '-c', long: '--compact', description: 'Compact output', optionKey: 'compact' },
];

export async function handleSnapshot(
  args: string[],
  bm: BrowserManager
): Promise<string> {
  const page = bm.getPage();
  
  // Simple ariaSnapshot implementation
  try {
    const ariaText = await page.locator('body').ariaSnapshot();
    if (!ariaText || ariaText.trim().length === 0) {
      return '(no accessible elements found)';
    }
    return ariaText;
  } catch (err: any) {
    return `(snapshot failed: ${err.message})`;
  }
}
