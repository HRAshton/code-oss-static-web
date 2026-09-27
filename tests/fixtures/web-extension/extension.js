'use strict';

const vscode = require('vscode');

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('codeOssStaticWebTest.markReady', async () => {
      await context.globalState.update('qualificationMarker', 'ready');
      vscode.window.showInformationMessage('Static web test extension activated');
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
