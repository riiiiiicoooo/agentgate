/**
 * Secret Commands
 *
 * agentgate secret request/rotate/list commands
 */

import { Command } from 'commander';
import AgentGateClient from '../../sdk/src';

export function secretCommands(program: Command): void {
  const secret = program
    .command('secret')
    .description('Secret management');

  secret
    .command('request')
    .description('Request a secret lease')
    .requiredOption('--name <name>', 'Secret name')
    .option('--ttl <seconds>', 'Time-to-live in seconds', '3600')
    .option('--reason <reason>', 'Business justification')
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

        const response = await client.request('POST', '/api/v1/secrets/request', {
          secret_name: options.name,
          ttl_seconds: parseInt(options.ttl),
          justification: options.reason,
        });

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const lease = response as any;
          console.log(`Secret lease created`);
          console.log(`Lease ID: ${lease.lease_id}`);
          console.log(`Secret: ${lease.secret_value}`);
          console.log(`Expires: ${lease.expires_at}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  secret
    .command('renew <lease-id>')
    .description('Renew a secret lease')
    .option('--ttl <seconds>', 'Additional time in seconds', '3600')
    .option('--json', 'Output as JSON')
    .action(async (leaseId, options) => {
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
          `/api/v1/secrets/${leaseId}/renew`,
          {
            lease_id: leaseId,
            additional_ttl_seconds: parseInt(options.ttl),
          },
        );

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          console.log(`Lease renewed successfully`);
          console.log(`New expiry: ${(response as any).expires_at}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  secret
    .command('revoke <lease-id>')
    .description('Revoke a secret lease')
    .action(async (leaseId) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        await client.request('POST', `/api/v1/secrets/${leaseId}/revoke`);

        console.log(`Lease revoked successfully`);
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  secret
    .command('status <secret-name>')
    .description('Get secret status')
    .option('--json', 'Output as JSON')
    .action(async (secretName, options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        const response = await client.request('GET', `/api/v1/secrets/${secretName}/status`);

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const status = response as any;
          console.log(`Secret: ${status.secret_name}`);
          console.log(`Version: ${status.latest_version}`);
          console.log(`Created: ${status.created_at}`);
          console.log(`Last rotated: ${status.last_rotated || 'Never'}`);
          console.log(`Rotation enabled: ${status.rotation_enabled}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  secret
    .command('rotate <secret-name>')
    .description('Rotate a secret')
    .option('--strategy <strategy>', 'Rotation strategy', 'random')
    .option('--value <value>', 'Custom new value')
    .option('--json', 'Output as JSON')
    .action(async (secretName, options) => {
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
          `/api/v1/secrets/${secretName}/rotate`,
          {
            secret_name: secretName,
            new_value: options.value,
            rotation_strategy: options.strategy,
          },
        );

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          console.log(`Secret rotated successfully`);
          console.log(`New version: ${(response as any).new_version}`);
          console.log(`Rotated at: ${(response as any).rotated_at}`);
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });
}
