'use strict';

const vscode = require('vscode');

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('codeOssStaticWebTest.markReady', async () => {
      await context.globalState.update('qualificationMarker', 'ready');
      vscode.window.showInformationMessage('Static web test extension activated');
    }),
    vscode.commands.registerCommand('codeOssStaticWebTest.readMarker', () => {
      return context.globalState.get('qualificationMarker', 'missing');
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
