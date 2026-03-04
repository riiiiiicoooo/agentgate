/**
 * Policy Commands
 *
 * agentgate policy create/test/simulate commands
 */

import { Command } from 'commander';
import * as fs from 'fs';
import AgentGateClient from '../../sdk/src';

export function policyCommands(program: Command): void {
  const policy = program
    .command('policy')
    .description('Policy management');

  policy
    .command('create')
    .description('Create a new policy')
    .option('--file <path>', 'Policy file (JSON)')
    .option('--name <name>', 'Policy name')
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

        let policyData: any;

        if (options.file) {
          const content = fs.readFileSync(options.file, 'utf-8');
          policyData = JSON.parse(content);
        } else if (options.name) {
          policyData = {
            name: options.name,
            rules: [],
          };
        } else {
          console.error('Error: --file or --name is required');
          process.exit(1);
        }

        const response = await client.request('POST', '/api/v1/policies', policyData);

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          console.log('Policy created successfully');
          console.log(`Policy ID: ${(response as any).policy_id}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  policy
    .command('list')
    .description('List policies')
    .option('--offset <n>', 'Result offset', '0')
    .option('--limit <n>', 'Results per page', '50')
    .option('--tag <tag>', 'Filter by tag')
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

        let url = `/api/v1/policies?offset=${options.offset}&limit=${options.limit}`;
        if (options.tag) {
          url += `&tag=${encodeURIComponent(options.tag)}`;
        }

        const response = await client.request('GET', url);

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const policies = (response as any).policies;
          console.log(`Total policies: ${(response as any).total}`);
          policies.forEach((p: any) => {
            console.log(`${p.policy_id} - ${p.name}`);
          });
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  policy
    .command('simulate <policy-id>')
    .description('Simulate policy evaluation')
    .requiredOption('--agent-id <id>', 'Agent ID')
    .requiredOption('--action <action>', 'Action to test')
    .requiredOption('--resource <resource>', 'Resource to test')
    .option('--context <json>', 'Context data (JSON)')
    .option('--json', 'Output as JSON')
    .action(async (policyId, options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        const body = {
          agent_id: options.agentId,
          action: options.action,
          resource: options.resource,
          context: options.context ? JSON.parse(options.context) : undefined,
        };

        const response = await client.request(
          'POST',
          `/api/v1/policies/${policyId}/simulate`,
          body,
        );

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const decision = (response as any).decision;
          const color = decision === 'allow' ? '\x1b[32m' : '\x1b[31m';
          const reset = '\x1b[0m';

          console.log(`Decision: ${color}${decision.toUpperCase()}${reset}`);
          console.log(`Reason: ${(response as any).reason}`);
          console.log(`Matching rules: ${(response as any).matching_rules.length}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  policy
    .command('bind <policy-id> <agent-id>')
    .description('Bind policy to agent')
    .action(async (policyId, agentId) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        await client.request('POST', `/api/v1/policies/${policyId}/bind/${agentId}`);

        console.log(`Policy bound to agent successfully`);
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });
}
