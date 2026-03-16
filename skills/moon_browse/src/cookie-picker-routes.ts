/**
 * Cookie picker route handler — simplified for Moon-Stack
 */

import type { BrowserManager } from './browser-manager';
import { getCookiePickerHTML } from './cookie-picker-ui';

export async function handleCookiePickerRoute(
  url: URL,
  req: Request,
  bm: BrowserManager,
): Promise<Response> {
  const pathname = url.pathname;
  const port = bm.serverPort || 3000;

  if (pathname === '/cookie-picker' && req.method === 'GET') {
    const html = getCookiePickerHTML(port);
    return new Response(html, {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  // Placeholder for other routes
  return new Response('Not implemented', { status: 501 });
}
