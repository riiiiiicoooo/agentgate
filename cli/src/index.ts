#!/usr/bin/env node

/**
 * AgentGate CLI
 *
 * Command-line interface for AgentGate management.
 */

import { Command } from 'commander';
import { agentCommands } from './commands/agent';
import { policyCommands } from './commands/policy';
import { secretCommands } from './commands/secret';
import { auditCommands } from './commands/audit';

const program = new Command();

program
  .name('agentgate')
  .description('AgentGate - AI Agent Authentication & Authorization Gateway')
  .version('1.0.0')
  .option(
    '--base-url <url>',
    'AgentGate API base URL',
    process.env.AGENTGATE_URL || 'http://localhost:8000',
  )
  .option(
    '--api-key <key>',
    'API key for authentication',
    process.env.AGENTGATE_API_KEY,
  )
  .option(
    '--token <token>',
    'Bearer token for authentication',
    process.env.AGENTGATE_TOKEN,
  );

// Add command groups
agentCommands(program);
policyCommands(program);
secretCommands(program);
auditCommands(program);

// Parse and run
program.parse(process.argv);

if (!process.argv.slice(2).length) {
  program.outputHelp();
}

export default program;
