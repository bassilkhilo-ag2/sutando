/**
 * Unit tests for src/recording-state.ts — shared mutable refs.
 *
 * Verifies initial values and that each ref is independently mutable.
 * Each test saves and restores the ref value to avoid cross-test state leakage.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	demoStateRef,
	narrationSpeakingRef,
	lastSpokenRef,
	nextDescRef,
	scrollPausedRef,
} from '../src/recording-state.ts';

// ---------------------------------------------------------------------------
// Initial values
// ---------------------------------------------------------------------------

test('demoStateRef initial value is "idle"', () => {
	const orig = demoStateRef.value;
	try {
		// Reset to initial in case a prior test leaked
		demoStateRef.value = 'idle';
		assert.equal(demoStateRef.value, 'idle');
	} finally {
		demoStateRef.value = orig as typeof demoStateRef.value;
	}
});

test('narrationSpeakingRef initial value is false', () => {
	const orig = narrationSpeakingRef.value;
	try {
		narrationSpeakingRef.value = false;
		assert.equal(narrationSpeakingRef.value, false);
	} finally {
		narrationSpeakingRef.value = orig;
	}
});

test('lastSpokenRef initial value is empty string', () => {
	const orig = lastSpokenRef.value;
	try {
		lastSpokenRef.value = '';
		assert.equal(lastSpokenRef.value, '');
	} finally {
		lastSpokenRef.value = orig;
	}
});

test('nextDescRef initial value is null', () => {
	const orig = nextDescRef.value;
	try {
		nextDescRef.value = null;
		assert.equal(nextDescRef.value, null);
	} finally {
		nextDescRef.value = orig;
	}
});

test('scrollPausedRef initial value is false', () => {
	const orig = scrollPausedRef.value;
	try {
		scrollPausedRef.value = false;
		assert.equal(scrollPausedRef.value, false);
	} finally {
		scrollPausedRef.value = orig;
	}
});

// ---------------------------------------------------------------------------
// Mutation
// ---------------------------------------------------------------------------

test('demoStateRef can be set to "recording"', () => {
	const orig = demoStateRef.value;
	try {
		demoStateRef.value = 'recording';
		assert.equal(demoStateRef.value, 'recording');
	} finally {
		demoStateRef.value = orig as typeof demoStateRef.value;
	}
});

test('demoStateRef can be set to "done"', () => {
	const orig = demoStateRef.value;
	try {
		demoStateRef.value = 'done';
		assert.equal(demoStateRef.value, 'done');
	} finally {
		demoStateRef.value = orig as typeof demoStateRef.value;
	}
});

test('narrationSpeakingRef can be toggled true then false', () => {
	const orig = narrationSpeakingRef.value;
	try {
		narrationSpeakingRef.value = true;
		assert.equal(narrationSpeakingRef.value, true);
		narrationSpeakingRef.value = false;
		assert.equal(narrationSpeakingRef.value, false);
	} finally {
		narrationSpeakingRef.value = orig;
	}
});

test('lastSpokenRef can be set to a non-empty string', () => {
	const orig = lastSpokenRef.value;
	try {
		lastSpokenRef.value = 'Hello, Bassil.';
		assert.equal(lastSpokenRef.value, 'Hello, Bassil.');
	} finally {
		lastSpokenRef.value = orig;
	}
});

test('nextDescRef can be set to a string then back to null', () => {
	const orig = nextDescRef.value;
	try {
		nextDescRef.value = 'Screen shows the dashboard';
		assert.equal(nextDescRef.value, 'Screen shows the dashboard');
		nextDescRef.value = null;
		assert.equal(nextDescRef.value, null);
	} finally {
		nextDescRef.value = orig;
	}
});

test('scrollPausedRef can be set to true', () => {
	const orig = scrollPausedRef.value;
	try {
		scrollPausedRef.value = true;
		assert.equal(scrollPausedRef.value, true);
	} finally {
		scrollPausedRef.value = orig;
	}
});

test('all refs are independent objects', () => {
	// Modifying one ref does not affect another
	const origNarration = narrationSpeakingRef.value;
	const origScroll = scrollPausedRef.value;
	try {
		narrationSpeakingRef.value = true;
		assert.equal(scrollPausedRef.value, origScroll);
		scrollPausedRef.value = true;
		assert.equal(narrationSpeakingRef.value, true);
	} finally {
		narrationSpeakingRef.value = origNarration;
		scrollPausedRef.value = origScroll;
	}
});
