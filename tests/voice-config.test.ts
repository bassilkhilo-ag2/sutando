/**
 * Unit tests for src/voice-config.ts — VOICE_CONFIG_DEFAULTS and loadVoiceConfig.
 * resolveOwnerMode is covered separately in voice-config-owner-mode.test.ts.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { VOICE_CONFIG_DEFAULTS, loadVoiceConfig } from '../src/voice-config.ts';

// ---------------------------------------------------------------------------
// VOICE_CONFIG_DEFAULTS
// ---------------------------------------------------------------------------

test('VOICE_CONFIG_DEFAULTS has expected model', () => {
	assert.equal(VOICE_CONFIG_DEFAULTS.model, 'gemini-2.5-flash-native-audio-preview-12-2025');
});

test('VOICE_CONFIG_DEFAULTS has googleSearch: true', () => {
	assert.equal(VOICE_CONFIG_DEFAULTS.googleSearch, true);
});

test('VOICE_CONFIG_DEFAULTS has owner_mode: false', () => {
	assert.equal(VOICE_CONFIG_DEFAULTS.owner_mode, false);
});

test('VOICE_CONFIG_DEFAULTS has empty channels', () => {
	assert.deepEqual(VOICE_CONFIG_DEFAULTS.channels, {});
});

// ---------------------------------------------------------------------------
// loadVoiceConfig — missing file
// ---------------------------------------------------------------------------

test('loadVoiceConfig returns defaults when file does not exist', () => {
	const result = loadVoiceConfig('/tmp/definitely-no-such-voice-config-xyzzy.json');
	assert.equal(result.model, VOICE_CONFIG_DEFAULTS.model);
	assert.equal(result.googleSearch, VOICE_CONFIG_DEFAULTS.googleSearch);
	assert.equal(result.owner_mode, VOICE_CONFIG_DEFAULTS.owner_mode);
	assert.deepEqual(result.channels, {});
});

// ---------------------------------------------------------------------------
// loadVoiceConfig — valid JSON
// ---------------------------------------------------------------------------

let _dir: string | undefined;

function mkTmp(): string {
	const d = join('/tmp', `voice-cfg-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	mkdirSync(d, { recursive: true });
	_dir = d;
	return d;
}

function cleanTmp(): void {
	if (_dir) {
		rmSync(_dir, { recursive: true, force: true });
		_dir = undefined;
	}
}

test('loadVoiceConfig returns defaults when file has empty object', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, '{}');
		const result = loadVoiceConfig(p);
		assert.equal(result.model, VOICE_CONFIG_DEFAULTS.model);
		assert.equal(result.googleSearch, VOICE_CONFIG_DEFAULTS.googleSearch);
		assert.equal(result.owner_mode, false);
		assert.deepEqual(result.channels, {});
	} finally { cleanTmp(); }
});

test('loadVoiceConfig overrides model when file specifies one', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, JSON.stringify({ model: 'gemini-3.0-ultra' }));
		const result = loadVoiceConfig(p);
		assert.equal(result.model, 'gemini-3.0-ultra');
	} finally { cleanTmp(); }
});

test('loadVoiceConfig overrides googleSearch when file specifies false', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, JSON.stringify({ googleSearch: false }));
		const result = loadVoiceConfig(p);
		assert.equal(result.googleSearch, false);
	} finally { cleanTmp(); }
});

test('loadVoiceConfig overrides owner_mode when file specifies true', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, JSON.stringify({ owner_mode: true }));
		const result = loadVoiceConfig(p);
		assert.equal(result.owner_mode, true);
	} finally { cleanTmp(); }
});

test('loadVoiceConfig takes channels verbatim from file', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		const channels = { '1234567890': { owner_mode: true } };
		writeFileSync(p, JSON.stringify({ channels }));
		const result = loadVoiceConfig(p);
		assert.deepEqual(result.channels, channels);
	} finally { cleanTmp(); }
});

test('loadVoiceConfig fills missing keys from defaults on partial file', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, JSON.stringify({ owner_mode: true }));
		const result = loadVoiceConfig(p);
		// model and googleSearch come from defaults
		assert.equal(result.model, VOICE_CONFIG_DEFAULTS.model);
		assert.equal(result.googleSearch, VOICE_CONFIG_DEFAULTS.googleSearch);
		// owner_mode from file
		assert.equal(result.owner_mode, true);
	} finally { cleanTmp(); }
});

test('loadVoiceConfig channels defaults to {} when file has no channels key', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, JSON.stringify({ model: 'gemini-3.0-ultra' }));
		const result = loadVoiceConfig(p);
		assert.deepEqual(result.channels, {});
	} finally { cleanTmp(); }
});

test('loadVoiceConfig accepts multiple channels with mixed owner_mode', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		const channels = {
			'111': { owner_mode: true },
			'222': { owner_mode: false },
			'333': {},
		};
		writeFileSync(p, JSON.stringify({ channels }));
		const result = loadVoiceConfig(p);
		assert.deepEqual(result.channels, channels);
	} finally { cleanTmp(); }
});

// ---------------------------------------------------------------------------
// loadVoiceConfig — corrupted / invalid JSON
// ---------------------------------------------------------------------------

test('loadVoiceConfig returns defaults on invalid JSON', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, 'not json }{');
		const result = loadVoiceConfig(p);
		assert.equal(result.model, VOICE_CONFIG_DEFAULTS.model);
		assert.equal(result.googleSearch, VOICE_CONFIG_DEFAULTS.googleSearch);
		assert.equal(result.owner_mode, false);
		assert.deepEqual(result.channels, {});
	} finally { cleanTmp(); }
});

test('loadVoiceConfig returns defaults on truncated JSON', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, '{"model": "gemini-3');
		const result = loadVoiceConfig(p);
		assert.equal(result.model, VOICE_CONFIG_DEFAULTS.model);
	} finally { cleanTmp(); }
});

test('loadVoiceConfig returns defaults on empty file', () => {
	const dir = mkTmp();
	try {
		const p = join(dir, 'config.json');
		writeFileSync(p, '');
		const result = loadVoiceConfig(p);
		assert.equal(result.model, VOICE_CONFIG_DEFAULTS.model);
		assert.deepEqual(result.channels, {});
	} finally { cleanTmp(); }
});
