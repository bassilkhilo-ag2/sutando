import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Pin the #1381 item-3 fix: phone bridge must honor [channel: <id>] redirect
// markers in task results. The other 5 surfaces (discord, slack, telegram,
// voice/task-bridge) already strip these — phone was the one gap. When the
// first line of a result body matches [channel: <id>], the phone bridge must
// NOT narrate the body to the caller; instead it writes a proactive-*.txt file
// so discord-bridge can route it to the right channel.

const SRC = readFileSync(
	join(import.meta.dirname ?? '.', '..', 'skills/phone-conversation/scripts/conversation-server.ts'),
	'utf-8',
);

describe('conversation-server [channel:] redirect (#1381 item 3)', () => {
	it('declares a _channelMatch variable that scans for [channel: ...] in result', () => {
		// The variable name + the literal [channel: fragment inside the regex
		assert.match(
			SRC,
			/_channelMatch\s*=\s*\/.*\[channel:/,
			'conversation-server.ts must define _channelMatch by applying a [channel:] regex to `result`',
		);
	});

	it('extracts the channel id into _channelId', () => {
		assert.match(
			SRC,
			/const _channelId\s*=\s*_channelMatch\[1\]\.trim\(\)/,
			'channel-redirect block must extract the channel id via _channelMatch[1].trim()',
		);
	});

	it('writes a proactive-*.txt redirect file to RESULTS_DIR', () => {
		assert.match(
			SRC,
			/writeFileSync\(\s*_proactivePath\s*,\s*`\[channel:\s*\$\{_channelId\}\]\\n\$\{_body\}`\s*\)/,
			'channel-redirect block must write `[channel: ${_channelId}]\\n${_body}` to RESULTS_DIR',
		);
	});

	it('proactive path is proactive-${Date.now()}.txt inside RESULTS_DIR', () => {
		assert.match(
			SRC,
			/join\(\s*RESULTS_DIR\s*,\s*`proactive-\$\{Date\.now\(\)\}\.txt`\s*\)/,
			'proactive file must use RESULTS_DIR + proactive-${Date.now()}.txt — matches discord-bridge poll pattern',
		);
	});

	it('narrates "Forwarded. Nothing else to report to the caller." instead of the body', () => {
		assert.match(
			SRC,
			/Forwarded\. Nothing else to report to the caller\./,
			'phone must narrate a neutral "Forwarded" message — not the literal body or channel id',
		);
	});

	it('redirect branch returns early — anti-hallucination wrapper is skipped', () => {
		// The block must contain `return;` so we never fall through to `isEmpty`/`injectedText`.
		const blockStart = SRC.indexOf('_channelMatch = /');
		const blockRegion = SRC.slice(blockStart, blockStart + 800);
		assert.ok(
			blockRegion.includes('return;'),
			'[channel:] redirect block must contain return; — anti-hallucination wrapper must not run for redirected results',
		);
	});

	it('cache write (taskResultCache.set) precedes the channel-redirect check', () => {
		// Result must be cached BEFORE redirect so replay also redirects.
		const cacheIdx = SRC.indexOf('callSession.taskResultCache.set(taskDescription, result)');
		const redirectIdx = SRC.indexOf('_channelMatch = /');
		assert.ok(cacheIdx > 0, 'taskResultCache.set must be present');
		assert.ok(redirectIdx > 0, '_channelMatch redirect check must be present');
		assert.ok(
			cacheIdx < redirectIdx,
			'taskResultCache.set must precede _channelMatch check — so replayed results also redirect',
		);
	});
});
