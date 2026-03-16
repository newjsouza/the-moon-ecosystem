/**
 * Command registry — simplified for Moon-Stack
 */
export const READ_COMMANDS = new Set([
  'text', 'html', 'links', 'forms', 'accessibility', 'js', 'eval', 'css', 'attrs',
  'console', 'network', 'cookies', 'storage', 'perf', 'dialog', 'is',
]);
export const WRITE_COMMANDS = new Set([
  'goto', 'back', 'forward', 'reload', 'click', 'fill', 'select', 'hover', 'type',
  'press', 'scroll', 'wait', 'viewport', 'cookie', 'cookie-import',
  'cookie-import-browser', 'header', 'useragent', 'upload', 'dialog-accept',
  'dialog-dismiss',
]);
export const META_COMMANDS = new Set([
  'tabs', 'tab', 'newtab', 'closetab', 'status', 'stop', 'restart', 'screenshot',
  'pdf', 'responsive', 'chain', 'diff', 'url', 'snapshot',
]);
export const ALL_COMMANDS = new Set([...READ_COMMANDS, ...WRITE_COMMANDS, ...META_COMMANDS]);

export const COMMAND_DESCRIPTIONS: Record<string, { category: string; description: string; usage?: string }> = {
  'goto': { category: 'Navigation', description: 'Navigate to URL', usage: 'goto <url>' },
  'snapshot': { category: 'Snapshot', description: 'Accessibility tree with @e refs', usage: 'snapshot [flags]' },
  'screenshot': { category: 'Visual', description: 'Save screenshot', usage: 'screenshot [path]' },
  'click': { category: 'Interaction', description: 'Click element', usage: 'click <sel>' },
  'fill': { category: 'Interaction', description: 'Fill input', usage: 'fill <sel> <val>' },
  'text': { category: 'Reading', description: 'Cleaned page text' },
  'html': { category: 'Reading', description: 'Page HTML' },
  'console': { category: 'Inspection', description: 'Console messages', usage: 'console [--errors]' },
  'links': { category: 'Reading', description: 'All links as "text → href"' },
  'stop': { category: 'Server', description: 'Shutdown server' },
};
