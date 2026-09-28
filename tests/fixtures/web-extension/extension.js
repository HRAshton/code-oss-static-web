'use strict';

const vscode = require('vscode');

const storageFileName = 'qualification-storage.txt';
const storageValue = 'browser-filesystem-ready';

async function storageUri(context) {
  await vscode.workspace.fs.createDirectory(context.globalStorageUri);
  return vscode.Uri.joinPath(context.globalStorageUri, storageFileName);
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('codeOssStaticWebTest.markReady', async () => {
      await context.globalState.update('qualificationMarker', 'ready');
      vscode.window.showInformationMessage('Static web test extension activated');
    }),
    vscode.commands.registerCommand('codeOssStaticWebTest.readMarker', () => {
      return context.globalState.get('qualificationMarker', 'missing');
    }),
    vscode.commands.registerCommand('codeOssStaticWebTest.writeStorageFile', async () => {
      const uri = await storageUri(context);
      await vscode.workspace.fs.writeFile(uri, new TextEncoder().encode(storageValue));
      return storageValue;
    }),
    vscode.commands.registerCommand('codeOssStaticWebTest.readStorageFile', async () => {
      try {
        const uri = await storageUri(context);
        const data = await vscode.workspace.fs.readFile(uri);
        return new TextDecoder().decode(data);
      } catch {
        return 'missing';
      }
    }),
    vscode.commands.registerCommand('codeOssStaticWebTest.probeLanguageService', async () => {
      const document = await vscode.workspace.openTextDocument({
        language: 'javascript',
        content: 'const qualificationValue = Math.',
      });
      const position = document.positionAt(document.getText().length);
      const result = await vscode.commands.executeCommand(
        'vscode.executeCompletionItemProvider',
        document.uri,
        position
      );
      if (Array.isArray(result)) {
        return result.length;
      }
      return result && Array.isArray(result.items) ? result.items.length : 0;
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
