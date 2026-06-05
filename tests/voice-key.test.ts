/**
 * Unit tests for src/voice-key.ts — voiceApiKey().
 *
 * Chain: GEMINI_VOICE_API_KEY → GEMINI_API_KEY → ''.
 * All env manipulation is restored in finally blocks.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

// voice-key.ts reads env at call time (no module-scope cache), so we can
// manipulate env vars and call voiceApiKey() directly without cache-busting.
import { voiceApiKey } from '../src/voice-key.ts';

function clearVoiceEnv() {
	delete process.env.GEMINI_VOICE_API_KEY;
	delete process.env.GEMINI_API_KEY;
}

test('voiceApiKey returns empty string when neither env var is set', () => {
	clearVoiceEnv();
	try {
		assert.equal(voiceApiKey(), '');
	} finally {
		clearVoiceEnv();
	}
});

test('voiceApiKey returns GEMINI_API_KEY when GEMINI_VOICE_API_KEY is not set', () => {
	clearVoiceEnv();
	process.env.GEMINI_API_KEY = 'main-key-abc';
	try {
		assert.equal(voiceApiKey(), 'main-key-abc');
	} finally {
		clearVoiceEnv();
	}
});

test('voiceApiKey returns GEMINI_VOICE_API_KEY when set', () => {
	clearVoiceEnv();
	process.env.GEMINI_VOICE_API_KEY = 'voice-key-xyz';
	try {
		assert.equal(voiceApiKey(), 'voice-key-xyz');
	} finally {
		clearVoiceEnv();
	}
});

test('voiceApiKey prefers GEMINI_VOICE_API_KEY over GEMINI_API_KEY', () => {
	clearVoiceEnv();
	process.env.GEMINI_VOICE_API_KEY = 'voice-key-xyz';
	process.env.GEMINI_API_KEY = 'main-key-abc';
	try {
		assert.equal(voiceApiKey(), 'voice-key-xyz');
	} finally {
		clearVoiceEnv();
	}
});

test('voiceApiKey returns GEMINI_API_KEY when GEMINI_VOICE_API_KEY is empty string', () => {
	clearVoiceEnv();
	// Empty string is falsy — chain falls through to GEMINI_API_KEY
	process.env.GEMINI_VOICE_API_KEY = '';
	process.env.GEMINI_API_KEY = 'main-key-abc';
	try {
		assert.equal(voiceApiKey(), 'main-key-abc');
	} finally {
		clearVoiceEnv();
	}
});

test('voiceApiKey returns string type in all cases', () => {
	clearVoiceEnv();
	try {
		assert.equal(typeof voiceApiKey(), 'string');
	} finally {
		clearVoiceEnv();
	}
});
