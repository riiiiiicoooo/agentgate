/**
 * Audit Commands
 *
 * agentgate audit query/export commands
 */

import { Command } from 'commander';
import * as fs from 'fs';
import AgentGateClient from '../../sdk/src';

export function auditCommands(program: Command): void {
  const audit = program
    .command('audit')
    .description('Audit log operations');

  audit
    .command('query')
    .description('Query audit logs')
    .option('--event-type <type>', 'Filter by event type')
    .option('--actor <agent-id>', 'Filter by actor')
    .option('--resource <resource>', 'Filter by resource')
    .option('--severity <level>', 'Filter by severity')
    .option('--offset <n>', 'Result offset', '0')
    .option('--limit <n>', 'Results per page', '50')
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

        const query = {
          event_type: options.eventType,
          actor_agent_id: options.actor,
          resource_type: options.resource,
          severity: options.severity,
          offset: parseInt(options.offset),
          limit: parseInt(options.limit),
        };

        const response = await client.request('POST', '/api/v1/audit/query', query);

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const result = response as any;
          console.log(`Total events: ${result.total}`);
          console.log(`Query time: ${result.query_time_ms.toFixed(2)}ms`);
          console.log('');

          result.events.forEach((event: any) => {
            console.log(`[${event.timestamp}] ${event.event_type}`);
            console.log(`  Actor: ${event.actor_agent_id}`);
            console.log(`  Action: ${event.action} on ${event.resource_id}`);
            console.log(`  Status: ${event.status} (${event.severity})`);
          });
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  audit
    .command('export')
    .description('Export audit logs as CSV')
    .option('--output <path>', 'Output file path', 'audit_export.csv')
    .option('--event-type <type>', 'Filter by event type')
    .option('--start-time <iso>', 'Start time (ISO 8601)')
    .option('--end-time <iso>', 'End time (ISO 8601)')
    .action(async (options) => {
      try {
        const client = new AgentGateClient(
          process.env.AGENTGATE_URL || 'http://localhost:8000',
          process.env.AGENTGATE_API_KEY,
        );

        if (process.env.AGENTGATE_TOKEN) {
          client.setAccessToken(process.env.AGENTGATE_TOKEN);
        }

        const url = new URL(`${process.env.AGENTGATE_URL || 'http://localhost:8000'}/api/v1/audit/export/csv`);

        if (options.eventType) {
          url.searchParams.append('event_type', options.eventType);
        }
        if (options.startTime) {
          url.searchParams.append('start_time', options.startTime);
        }
        if (options.endTime) {
          url.searchParams.append('end_time', options.endTime);
        }

        const response = await fetch(url.toString(), {
          headers: {
            Authorization: process.env.AGENTGATE_TOKEN ? `Bearer ${process.env.AGENTGATE_TOKEN}` : '',
            'X-API-Key': process.env.AGENTGATE_API_KEY || '',
          },
        });

        if (!response.ok) {
          throw new Error(`Export failed: ${response.statusText}`);
        }

        const content = await response.text();
        fs.writeFileSync(options.output, content);

        console.log(`Audit logs exported to: ${options.output}`);
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  audit
    .command('stats')
    .description('Get audit statistics')
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

        const response = await client.request('GET', '/api/v1/audit/stats');

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const stats = response as any;
          console.log(`Total events: ${stats.total_events}`);
          console.log(`Success events: ${stats.success_events}`);
          console.log(`Failed events: ${stats.failure_events}`);
          console.log(`Success rate: ${stats.success_rate.toFixed(2)}%`);
          console.log(`Unique actors: ${stats.unique_actors}`);
          console.log('');
          console.log('Event types:');

          Object.entries(stats.event_types).forEach(([type, count]) => {
            console.log(`  ${type}: ${count}`);
          });
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });

  audit
    .command('compliance')
    .description('Generate compliance report')
    .requiredOption('--framework <framework>', 'Compliance framework (SOC2, HIPAA, etc.)')
    .requiredOption('--organization <org>', 'Organization name')
    .option('--days <n>', 'Report period in days', '30')
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

        const url = `/api/v1/audit/compliance/generate?framework=${options.framework}&organization=${options.organization}&period_days=${options.days}`;

        const response = await client.request('POST', url);

        if (options.json) {
          console.log(JSON.stringify(response, null, 2));
        } else {
          const report = response as any;
          console.log(`Compliance Report`);
          console.log(`Framework: ${report.compliance_framework}`);
          console.log(`Organization: ${report.organization}`);
          console.log(`Period: ${report.period_start} to ${report.period_end}`);
          console.log(`Generated: ${report.generated_at}`);
          console.log('');
          console.log('Summary:');
          console.log(report.summary);
          console.log('');
          console.log('Findings:');

          Object.entries(report.findings).forEach(([key, value]) => {
            console.log(`  ${key}: ${value}`);
          });
        }
      } catch (error) {
        console.error('Error:', (error as Error).message);
        process.exit(1);
      }
    });
}
