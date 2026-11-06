// Exercise the actual browser freshness function without a browser or network.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../dashboard/static/app.js'), 'utf8');
const start = source.indexOf('function isFreshTicker(');
const end = source.indexOf('function refreshFeedStatus()', start);
const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const quote = { status: 'verified', price: 100, age_seconds: 1, receivedAtMs: 1000 };
test('fresh verified quote is usable', () => assert.equal(context.isFreshTicker(quote, 2000), true));
test('quote expires even when stream stops sending', () => assert.equal(context.isFreshTicker(quote, 7000), false));
test('stale server status is never live', () => assert.equal(context.isFreshTicker({ ...quote, status: 'stale' }, 2000), false));
test('missing price is unavailable', () => assert.equal(context.isFreshTicker({ ...quote, price: null }, 2000), false));
test('metadata price cannot masquerade as a live quote', () => assert.equal(context.isFreshTicker({ price: 100, source: 'coingecko' }, 2000), false));
test('single source stays usable with its distinct label', () => assert.equal(context.isFreshTicker({ ...quote, status: 'single-source' }, 2000), true));
