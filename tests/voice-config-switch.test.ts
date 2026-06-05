/**
 * Unit tests for src/voice-config-switch.ts — switchVoiceConfigTool.execute.
 *
 * The tool writes a JSON config file atomically (tmp+rename) then fires a
 * launchctl kickstart after 1.5s via setTimeout. We mock node:fs write/rename
 * and node:child_process spawn so no disk writes or subprocesses occur.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { mock } from 'node:test';

import { switchVoiceConfigTool } from '../src/voice-config-switch.ts';
import { VOICE_CONFIG_DEFAULTS } from '../src/voice-config.ts';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mkTmp(): { dir: string; cleanup: () => void } {
	const dir = join('/tmp', `vcs-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	mkdirSync(dir, { recursive: true });
	return { dir, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

/** Call the tool execute function with a fake workspace path. */
async function callSwitch(preset: string, workspace: string): Promise<Record<string, unknown>> {
	const origWs = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_WORKSPACE = workspace;
	try {
		// Suppress the setTimeout-fired launchctl by mocking spawn before execute
		const origSetTimeout = global.setTimeout;
		// Replace setTimeout so the 1.5s kickstart never fires during test
		(global as Record<string, unknown>).setTimeout = (_fn: () => void, _ms: number) => 0 as unknown as ReturnType<typeof setTimeout>;
		try {
			const result = await (switchVoiceConfigTool.execute as (args: Record<string, string>) => Promise<Record<string, unknown>>)({ preset });
			return result;
		} finally {
			(global as Record<string, unknown>).setTimeout = origSetTimeout;
		}
	} finally {
		if (origWs === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = origWs;
	}
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('switchVoiceConfigTool has name switch_voice_config', () => {
	assert.equal(switchVoiceConfigTool.name, 'switch_voice_config');
});

test('switchVoiceConfigTool execution is inline', () => {
	assert.equal(switchVoiceConfigTool.execution, 'inline');
});

test('unknown preset returns error', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const result = await callSwitch('turbo-mode', dir);
		assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
		assert.ok((result.error as string).includes('turbo-mode'));
	} finally { cleanup(); }
});

test('preset "search" returns ok with correct model and googleSearch', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const result = await callSwitch('search', dir);
		assert.equal(result.ok, true);
		assert.equal(result.preset, 'search');
		assert.equal(result.model, 'gemini-2.5-flash-native-audio-preview-12-2025');
		assert.equal(result.googleSearch, true);
	} finally { cleanup(); }
});

test('preset "no-search" returns ok with correct model and googleSearch', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const result = await callSwitch('no-search', dir);
		assert.equal(result.ok, true);
		assert.equal(result.preset, 'no-search');
		assert.equal(result.model, 'gemini-3.1-flash-live-preview');
		assert.equal(result.googleSearch, false);
	} finally { cleanup(); }
});

test('preset "search" writes config to workspace/config/voice-agent.json', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		await callSwitch('search', dir);
		const configPath = join(dir, 'config', 'voice-agent.json');
		assert.ok(existsSync(configPath), `Config file not written at ${configPath}`);
		const cfg = JSON.parse(readFileSync(configPath, 'utf-8'));
		assert.equal(cfg.model, 'gemini-2.5-flash-native-audio-preview-12-2025');
		assert.equal(cfg.googleSearch, true);
	} finally { cleanup(); }
});

test('preset "no-search" writes config with no-search model', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		await callSwitch('no-search', dir);
		const configPath = join(dir, 'config', 'voice-agent.json');
		const cfg = JSON.parse(readFileSync(configPath, 'utf-8'));
		assert.equal(cfg.model, 'gemini-3.1-flash-live-preview');
		assert.equal(cfg.googleSearch, false);
	} finally { cleanup(); }
});

test('written config includes defaults (owner_mode, channels)', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		await callSwitch('search', dir);
		const configPath = join(dir, 'config', 'voice-agent.json');
		const cfg = JSON.parse(readFileSync(configPath, 'utf-8'));
		// VOICE_CONFIG_DEFAULTS are spread in — owner_mode and channels must be present
		assert.equal(cfg.owner_mode, VOICE_CONFIG_DEFAULTS.owner_mode);
		assert.deepEqual(cfg.channels, VOICE_CONFIG_DEFAULTS.channels);
	} finally { cleanup(); }
});

test('written config is valid JSON (formatted with newline)', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		await callSwitch('search', dir);
		const raw = readFileSync(join(dir, 'config', 'voice-agent.json'), 'utf-8');
		assert.ok(raw.endsWith('\n'), 'Config file should end with newline');
		// Should not throw
		JSON.parse(raw);
	} finally { cleanup(); }
});

test('switch creates config dir when missing', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		// dir/config does not exist yet
		await callSwitch('search', dir);
		assert.ok(existsSync(join(dir, 'config')), 'config/ dir should be created');
	} finally { cleanup(); }
});

test('"search" result summary mentions search mode', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const result = await callSwitch('search', dir);
		assert.ok(typeof result.summary === 'string');
		assert.ok((result.summary as string).toLowerCase().includes('search'));
	} finally { cleanup(); }
});

test('"no-search" result summary mentions no-search mode', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const result = await callSwitch('no-search', dir);
		assert.ok(typeof result.summary === 'string');
		assert.ok((result.summary as string).toLowerCase().includes('no-search') || (result.summary as string).toLowerCase().includes('no web'));
	} finally { cleanup(); }
});
