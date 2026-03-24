/**
 * Minimal VS Code API mock for Jest unit tests.
 * Provides just enough surface area for brain-connection.ts and extension.ts tests.
 */

const mockGetConfiguration = jest.fn().mockReturnValue({
    get: jest.fn().mockImplementation((_key: string, defaultValue: unknown) => defaultValue),
    update: jest.fn(),
});

export const workspace = {
    workspaceFolders: [{ name: 'test-workspace', uri: { fsPath: '/test' } }],
    getConfiguration: mockGetConfiguration,
};

export const window = {
    createOutputChannel: jest.fn().mockReturnValue({
        appendLine: jest.fn(),
        show: jest.fn(),
        dispose: jest.fn(),
    }),
    showWarningMessage: jest.fn(),
    showInformationMessage: jest.fn(),
    // Returns a disposable stub; tests that care about onDidChangeWindowState
    // can override this mock in their own beforeEach / jest.spyOn call.
    onDidChangeWindowState: jest.fn().mockReturnValue({ dispose: jest.fn() }),
};

export const commands = {
    executeCommand: jest.fn().mockResolvedValue(undefined),
};

export const env = {
    clipboard: {
        writeText: jest.fn().mockResolvedValue(undefined),
        readText: jest.fn().mockResolvedValue(''),
    },
};

// Named exports matching VS Code API usage
export default { workspace, window, commands, env };
