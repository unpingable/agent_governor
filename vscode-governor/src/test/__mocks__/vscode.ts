/**
 * Minimal vscode API mock for unit tests.
 */

export class Position {
  constructor(
    public readonly line: number,
    public readonly character: number
  ) {}
}

export class Range {
  constructor(
    public readonly start: Position,
    public readonly end: Position
  ) {}
}

export enum DiagnosticSeverity {
  Error = 0,
  Warning = 1,
  Information = 2,
  Hint = 3,
}

export class Diagnostic {
  public code: string | number | undefined;
  public source: string | undefined;

  constructor(
    public readonly range: Range,
    public message: string,
    public severity: DiagnosticSeverity = DiagnosticSeverity.Error
  ) {}
}

// TreeView types
export enum TreeItemCollapsibleState {
  None = 0,
  Collapsed = 1,
  Expanded = 2,
}

export class TreeItem {
  public description?: string;
  public tooltip?: string;
  public iconPath?: ThemeIcon;
  public command?: { command: string; title: string; arguments?: unknown[] };

  constructor(
    public label: string,
    public collapsibleState: TreeItemCollapsibleState = TreeItemCollapsibleState.None
  ) {}
}

export class ThemeIcon {
  constructor(public readonly id: string) {}
}

export class EventEmitter<T> {
  private listeners: Array<(e: T) => void> = [];

  event = (listener: (e: T) => void) => {
    this.listeners.push(listener);
    return { dispose: () => { this.listeners = this.listeners.filter(l => l !== listener); } };
  };

  fire(data: T): void {
    for (const listener of this.listeners) {
      listener(data);
    }
  }

  dispose(): void {
    this.listeners = [];
  }
}

const diagnosticCollections = new Map<string, Map<string, Diagnostic[]>>();

export const languages = {
  createDiagnosticCollection(name: string) {
    const store = new Map<string, Diagnostic[]>();
    diagnosticCollections.set(name, store);
    return {
      name,
      set(uri: { toString(): string }, diagnostics: Diagnostic[]) {
        store.set(uri.toString(), diagnostics);
      },
      delete(uri: { toString(): string }) {
        store.delete(uri.toString());
      },
      clear() {
        store.clear();
      },
      get(uri: { toString(): string }) {
        return store.get(uri.toString());
      },
      dispose() {
        store.clear();
      },
    };
  },
};

export const window = {
  createOutputChannel(_name: string) {
    return {
      appendLine(_msg: string) {},
      show() {},
      dispose() {},
    };
  },
  createStatusBarItem() {
    return {
      text: "",
      tooltip: "",
      command: "",
      show() {},
      hide() {},
      dispose() {},
    };
  },
  createTreeView(_id: string, options: { treeDataProvider: unknown; showCollapseAll?: boolean }) {
    return {
      treeDataProvider: options.treeDataProvider,
      dispose() {},
    };
  },
  showWarningMessage(_msg: string) {},
  showErrorMessage(_msg: string) {},
  get activeTextEditor() {
    return undefined;
  },
};

export const workspace = {
  getConfiguration(_section: string) {
    return {
      get<T>(key: string, defaultValue: T): T {
        return defaultValue;
      },
    };
  },
  workspaceFolders: undefined as undefined | Array<{ uri: { fsPath: string } }>,
  onDidSaveTextDocument(_handler: Function) {
    return { dispose() {} };
  },
};

export const commands = {
  registerCommand(_command: string, _callback: Function) {
    return { dispose() {} };
  },
};

export enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

export class Uri {
  constructor(public readonly fsPath: string) {}
  toString() {
    return this.fsPath;
  }
  static file(path: string) {
    return new Uri(path);
  }
}
