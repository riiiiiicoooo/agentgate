/**
 * Agent Commands
 *
 * agentgate agent register/list/revoke commands
 */

import { Command } from 'commander';
import AgentGateClient from '../../sdk/src';

export function agentCommands(program: Command): void {
  const agent = program
    .command('agent')
    .description('Agent management');

  agent
    .command('register')
    .description('Register a new agent')
    .option('--name <name>', 'Agent name')
    .option('--description <desc>', 'Agent description')
    .option('--scopes <scopes...>', 'Agent scopes')
    .option('--json', 'Output as JSON')
    .action(async (options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        if (!options.name) {
          console.error('Error: --name is required');
          process.exit(1);
        }

        const response = await client.request('POST', '/api/v1/agents', {
          name: options.name,
          description: options.description,
          scopes: options.scopes || ['default'],
          metadata: {},
        });

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          console.log(`Agent registered successfully`);
          console.log(`Agent ID: ${(response as any).agent_id}`);
          console.log(`Client ID: ${(response as any).client_id}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  agent
    .command('list')
    .description('List all agents')
    .option('--offset <n>', 'Result offset', '0')
    .option('--limit <n>', 'Results per page', '50')
    .option('--status <status>', 'Filter by status')
    .option('--json', 'Output as JSON')
    .action(async (options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        let url = `/api/v1/agents?offset=${options.offset}&limit=${options.limit}`;
        if (options.status) {
          url += `&status_filter=${encodeURIComponent(options.status)}`;
        }

        const response = await client.request('GET', url);

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const agents = (response as any).agents;
          console.log(`Total agents: ${(response as any).total}`);
          console.log('');

          agents.forEach((agent: any) => {
            console.log(`${agent.agent_id}`);
            console.log(`  Name: ${agent.name}`);
            console.log(`  Status: ${agent.status}`);
            console.log(`  Created: ${agent.created_at}`);
          });
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  agent
    .command('rotate-credentials <agent-id>')
    .description('Rotate agent credentials')
    .option('--rotate-secret', 'Rotate client secret', true)
    .option('--rotate-keys', 'Rotate API keys', true)
    .option('--json', 'Output as JSON')
    .action(async (agentId, options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        const response = await client.request(
          'POST',
          `/api/v1/agents/${agentId}/rotate-credentials`,
          {
            rotate_client_secret: options.rotateSecret,
            rotate_api_keys: options.rotateKeys,
          },
        );

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          console.log('Credentials rotated successfully');
          if ((response as any).client_secret) {
            console.log(`New Client Secret: ${(response as any).client_secret}`);
          }
          if ((response as any).api_key) {
            console.log(`New API Key: ${(response as any).api_key}`);
          }
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  agent
    .command('revoke <agent-id>')
    .description('Revoke/archive an agent')
    .option('--json', 'Output as JSON')
    .action(async (agentId, options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        await client.request('DELETE', `/api/v1/agents/${agentId}`);

        if (!options.json) {
          console.log(`Agent ${agentId} archived successfully`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });
}
