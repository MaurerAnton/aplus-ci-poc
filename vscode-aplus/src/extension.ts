import * as vscode from 'vscode';
import * as path from 'path';
import * as cp from 'child_process';

export function activate(context: vscode.ExtensionContext) {
    console.log('A+ Language extension activated');

    // ── Run command: execute current .a+ file with a+ interpreter ──
    const runCmd = vscode.commands.registerCommand('aplus.run', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('No active editor.');
            return;
        }

        const filePath = editor.document.fileName;
        await editor.document.save();

        const outputChannel = vscode.window.createOutputChannel('A+ Run');
        outputChannel.show(true);
        outputChannel.appendLine(`Running: a+ ${filePath}`);

        const proc = cp.spawn('a+', [filePath], {
            cwd: path.dirname(filePath),
            env: { ...process.env }
        });

        proc.stdout.on('data', (data: Buffer) => {
            outputChannel.append(data.toString());
        });

        proc.stderr.on('data', (data: Buffer) => {
            outputChannel.append(data.toString());
        });

        proc.on('close', (code: number | null) => {
            if (code === 0) {
                outputChannel.appendLine(`\nProcess exited with code ${code}`);
            } else {
                outputChannel.appendLine(`\nProcess exited with code ${code}`);
                vscode.window.showErrorMessage(`A+ exited with code ${code}. See output for details.`);
            }
        });

        proc.on('error', (err: Error) => {
            outputChannel.appendLine(`Failed to start a+: ${err.message}`);
            vscode.window.showErrorMessage(`Failed to run a+: ${err.message}. Is a+ installed and in PATH?`);
        });
    });

    // ── Transpile command: transpile current .a+ file to Python and JS ──
    const transpileCmd = vscode.commands.registerCommand('aplus.transpile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('No active editor.');
            return;
        }

        const filePath = editor.document.fileName;
        await editor.document.save();

        const extDir = context.extensionPath;
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || path.dirname(filePath);

        // Look for transpile_aplus.py in common locations
        const possiblePaths = [
            path.join(workspaceRoot, 'transpile_aplus.py'),
            path.join(extDir, '..', '..', 'transpile_aplus.py'),
            path.join(extDir, 'transpile_aplus.py')
        ];

        const python = process.platform === 'win32' ? 'python' : 'python3';
        let transpilerPath: string | null = null;

        for (const p of possiblePaths) {
            try {
                await vscode.workspace.fs.stat(vscode.Uri.file(p));
                transpilerPath = p;
                break;
            } catch {
                // not found, try next
            }
        }

        if (!transpilerPath) {
            vscode.window.showErrorMessage(
                'Could not find transpile_aplus.py. Please ensure it is in your workspace root.'
            );
            return;
        }

        const baseName = path.basename(filePath, path.extname(filePath));
        const dirName = path.dirname(filePath);
        const pyOut = path.join(dirName, `${baseName}.py`);
        const jsOut = path.join(dirName, `${baseName}.js`);

        const outputChannel = vscode.window.createOutputChannel('A+ Transpile');
        outputChannel.show(true);
        outputChannel.appendLine(`Transpiling: ${filePath}`);
        outputChannel.appendLine(`  → Python: ${pyOut}`);
        outputChannel.appendLine(`  → JavaScript: ${jsOut}`);

        const proc = cp.spawn(python, [
            transpilerPath,
            '--input', filePath,
            '--output-py', pyOut,
            '--output-js', jsOut
        ]);

        proc.stdout.on('data', (data: Buffer) => {
            outputChannel.append(data.toString());
        });

        proc.stderr.on('data', (data: Buffer) => {
            outputChannel.append(data.toString());
        });

        proc.on('close', (code: number | null) => {
            if (code === 0) {
                outputChannel.appendLine('\nTranspilation completed successfully.');
                vscode.window.showInformationMessage(
                    `Transpiled to ${path.basename(pyOut)} and ${path.basename(jsOut)}`
                );
            } else {
                outputChannel.appendLine(`\nTranspilation failed with code ${code}`);
                vscode.window.showErrorMessage(`Transpilation failed. See output for details.`);
            }
        });

        proc.on('error', (err: Error) => {
            outputChannel.appendLine(`Failed to run transpiler: ${err.message}`);
            vscode.window.showErrorMessage(`Failed to run transpiler: ${err.message}`);
        });
    });

    context.subscriptions.push(runCmd, transpileCmd);
}

export function deactivate() {}
