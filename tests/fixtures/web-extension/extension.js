'use strict';

const vscode = require('vscode');

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('codeOssStaticWebTest.markReady', async () => {
      await context.globalState.update('qualificationMarker', 'ready');
      vscode.window.showInformationMessage('Static web test extension activated');
    }),
    vscode.commands.registerCommand('codeOssStaticWebTest.readMarker', () => {
      const marker = context.globalState.get('qualificationMarker', 'missing');
      vscode.window.showInformationMessage(`Static web test extension marker: ${marker}`);
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
