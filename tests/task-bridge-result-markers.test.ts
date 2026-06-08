import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Pin the #1381 item-2 fix: task-bridge must honor [no-send], [REPLIED], and
// [channel: <id>] result-body markers — the three markers that Python bridges
// handle via parse_markers() but task-bridge previously ignored, causing
// literal marker text to be narrated to the voice client.
//
// Tests are structural (source-level assertions) to avoid spinning up the full
// bridge — consistent with the existing task-bridge-*.test.ts suite pattern.

const SRC = readFileSync(
	join(import.meta.dirname ?? '.', '..', 'src/task-bridge.ts'),
	'utf-8',
);

describe('task-bridge result-body marker handling (#1381 item 2)', () => {
	describe('[no-send] skip marker', () => {
		it('tests for [no-send] marker via case-insensitive regex', () => {
			assert.match(
				SRC,
				/\[no-send\].*?i/,
				'task-bridge must test for [no-send] with /i flag — matches no-send / No-Send / NO-SEND',
			);
		});

		it('assigns no-send as a named reason string', () => {
			assert.match(
				SRC,
				/'no-send'/,
				"task-bridge must assign 'no-send' as the skip reason label — used in log output",
			);
		});
	});

	describe('[REPLIED] skip marker', () => {
		it('tests for [REPLIED] marker', () => {
			assert.match(
				SRC,
				/\[REPLIED\]/,
				'task-bridge must test for [REPLIED] marker',
			);
		});

		it('assigns REPLIED as a named reason string', () => {
			assert.match(
				SRC,
				/'\s*REPLIED\s*'/,
				"task-bridge must assign 'REPLIED' as the skip reason label — used in log output",
			);
		});
	});

	describe('[channel: <id>] redirect marker', () => {
		it('declares _tbChannelMatch via [channel:] regex', () => {
			assert.match(
				SRC,
				/_tbChannelMatch\s*=\s*\/.*\[channel:/,
				'task-bridge must define _tbChannelMatch by applying a [channel:] regex to result',
			);
		});

		it('extracts channel id into _tbChannelId', () => {
			assert.match(
				SRC,
				/const _tbChannelId\s*=\s*_tbChannelMatch\[1\]\.trim\(\)/,
				'channel-redirect block must extract the channel id via _tbChannelMatch[1].trim()',
			);
		});

		it('writes proactive-{ts}.txt inside RESULT_DIR', () => {
			assert.match(
				SRC,
				/join\(\s*RESULT_DIR\s*,\s*`proactive-\$\{Date\.now\(\)\}\.txt`\s*\)/,
				'task-bridge channel-redirect must write proactive-${Date.now()}.txt to RESULT_DIR',
			);
		});

		it('writes [channel: ${_tbChannelId}]\\n${_tbBody} to the proactive file', () => {
			assert.match(
				SRC,
				/writeFileSync\(\s*_tbProactivePath\s*,\s*`\[channel:\s*\$\{_tbChannelId\}\]\\n\$\{_tbBody\}`\s*\)/,
				'proactive file must start with [channel: ${_tbChannelId}] so discord-bridge routes it',
			);
		});

		it('logs channel-redirect with target channel id', () => {
			assert.match(
				SRC,
				/channel-redirect.*_tbChannelId/,
				'task-bridge must log the channel-redirect target for observability',
			);
		});
	});

	describe('ordering: skip markers before channel-redirect, both before voice narration', () => {
		it('[no-send] check precedes [channel:] check', () => {
			const noSendIdx = SRC.indexOf('[no-send]');
			const tbChannelIdx = SRC.indexOf('_tbChannelMatch');
			assert.ok(noSendIdx > 0, '[no-send] check must be present');
			assert.ok(tbChannelIdx > 0, '_tbChannelMatch redirect check must be present');
			assert.ok(
				noSendIdx < tbChannelIdx,
				'[no-send] skip must be checked before [channel:] redirect — skip is terminal',
			);
		});

		it('[deduped:] check precedes [no-send] check', () => {
			const dedupedIdx = SRC.indexOf('[deduped:');
			const noSendIdx = SRC.indexOf('[no-send]');
			assert.ok(
				dedupedIdx < noSendIdx,
				'[deduped:] must be checked before [no-send] — maintains existing marker precedence',
			);
		});

		it('[channel:] redirect check precedes the final voice narration (onResult)', () => {
			const tbChannelIdx = SRC.indexOf('_tbChannelMatch');
			// Use lastIndexOf — there are earlier onResult() calls for the
			// voice-offline path; the final one is the live-voice narration gate.
			const onResultIdx = SRC.lastIndexOf('onResult(result)');
			assert.ok(tbChannelIdx > 0, '_tbChannelMatch redirect check must be present');
			assert.ok(onResultIdx > 0, 'onResult(result) narration call must be present');
			assert.ok(
				tbChannelIdx < onResultIdx,
				'[channel:] redirect must short-circuit before the final onResult() narrates to voice',
			);
		});
	});
});
