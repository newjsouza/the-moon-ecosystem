/**
 * Chromium browser cookie import — Linux version for Moon-Stack
 * Supports GNOME Keyring (secretstorage) for cookie decryption
 *
 * This is a simplified Linux-compatible version.
 * For full macOS support, see the original gstack implementation.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

export interface BrowserInfo {
  name: string;
  dataDir: string;
  keychainService: string;
  aliases: string[];
}

export interface DomainEntry {
  domain: string;
  count: number;
}

export interface ImportResult {
  cookies: PlaywrightCookie[];
  count: number;
  failed: number;
  domainCounts: Record<string, number>;
}

export interface PlaywrightCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: number;
  secure: boolean;
  httpOnly: boolean;
  sameSite: 'Strict' | 'Lax' | 'None';
}

export class CookieImportError extends Error {
  constructor(
    message: string,
    public code: string,
    public action?: 'retry',
  ) {
    super(message);
    this.name = 'CookieImportError';
  }
}

// Linux browser paths
const LINUX_BROWSER_REGISTRY: BrowserInfo[] = [
  {
    name: 'Chrome',
    dataDir: '.config/google-chrome/',
    keychainService: 'Chrome Safe Storage',
    aliases: ['chrome', 'google-chrome'],
  },
  {
    name: 'Chromium',
    dataDir: '.config/chromium/',
    keychainService: 'Chromium Safe Storage',
    aliases: ['chromium'],
  },
  {
    name: 'Brave',
    dataDir: '.config/brave-browser/',
    keychainService: 'Brave Safe Storage',
    aliases: ['brave'],
  },
  {
    name: 'Edge',
    dataDir: '.config/microsoft-edge/',
    keychainService: 'Microsoft Edge Safe Storage',
    aliases: ['edge'],
  },
];

export function findInstalledBrowsers(): BrowserInfo[] {
  const home = os.homedir();
  return LINUX_BROWSER_REGISTRY.filter(b => {
    const dbPath = path.join(home, b.dataDir, 'Default', 'Cookies');
    try {
      return fs.existsSync(dbPath);
    } catch {
      return false;
    }
  });
}

export function listDomains(
  browserName: string,
  profile = 'Default',
): { domains: DomainEntry[]; browser: string } {
  // Placeholder - full implementation requires SQLite + decryption
  return { domains: [], browser: browserName };
}

export async function importCookies(
  browserName: string,
  domains: string[],
  profile = 'Default',
): Promise<ImportResult> {
  // Placeholder - requires Python secretstorage integration
  // This is handled by the Python MoonBrowserAgent instead
  return { cookies: [], count: 0, failed: 0, domainCounts: {} };
}
