/**
 * Config — simplified for Moon-Stack
 */
import * as fs from 'fs';
import * as path from 'path';

export interface BrowseConfig {
  projectDir: string;
  stateDir: string;
  stateFile: string;
  consoleLog: string;
  networkLog: string;
  dialogLog: string;
}

export function resolveConfig(): BrowseConfig {
  // Use environment variable if set, otherwise use default location
  let stateFile = process.env.BROWSE_STATE_FILE;

  if (!stateFile) {
    // Default to .gstack/browse.json in current working directory
    const cwd = process.cwd();
    const stateDir = path.join(cwd, '.gstack');
    stateFile = path.join(stateDir, 'browse.json');
  }

  const stateDir = path.dirname(stateFile);
  const projectDir = path.dirname(stateDir);

  return {
    projectDir,
    stateDir,
    stateFile,
    consoleLog: path.join(stateDir, 'browse-console.log'),
    networkLog: path.join(stateDir, 'browse-network.log'),
    dialogLog: path.join(stateDir, 'browse-dialog.log'),
  };
}

export function ensureStateDir(config: BrowseConfig): void {
  try {
    fs.mkdirSync(config.stateDir, { recursive: true, mode: 0o755 });
  } catch (err: any) {
    if (err.code === 'EACCES' || err.code === 'EPERM') {
      throw new Error(`Cannot create state directory ${config.stateDir}: permission denied`);
    }
    throw err;
  }
}

export function readVersionHash(): string | null {
  return null;
}
