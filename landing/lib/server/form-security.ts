import { createHmac, randomBytes, timingSafeEqual, createHash } from 'node:crypto';

export function issueOperatorCookie(passcode: string, now = Date.now()): string {
  if (!passcode) throw new Error('Operator authentication is not configured');
  const payload = `${Math.floor(now / 1000)}.${randomBytes(16).toString('hex')}`;
  return `${payload}.${createHmac('sha256', passcode).update(payload).digest('hex')}`;
}

export function verifyOperatorCookie(value: string | undefined, passcode: string, now = Date.now()): boolean {
  if (!value || !passcode) return false;
  const parts = value.split('.');
  if (parts.length !== 3 || !/^\d+$/.test(parts[0]) || !/^[a-f0-9]{32}$/.test(parts[1]) || !/^[a-f0-9]{64}$/.test(parts[2])) return false;
  const age = now / 1000 - Number(parts[0]);
  if (age < 0 || age > 604800) return false;
  const expected = createHmac('sha256', passcode).update(`${parts[0]}.${parts[1]}`).digest();
  return timingSafeEqual(Uint8Array.from(Buffer.from(parts[2], 'hex')), Uint8Array.from(expected));
}

export function matchesOperatorPasscode(value: unknown, passcode: string): boolean {
  if (!passcode || typeof value !== 'string') return false;
  const a = Buffer.from(value.trim()), b = Buffer.from(passcode);
  return a.length === b.length && timingSafeEqual(Uint8Array.from(a), Uint8Array.from(b));
}

export function sameOrigin(origin: unknown, host: unknown): boolean {
  if (!origin) return true;
  try { return typeof origin === 'string' && new URL(origin).host === host; } catch { return false; }
}

const recent: Array<{ at: number; client: string }> = [];
const duplicates = new Map<string, number>();
export function allowSubmission(data: unknown, client: string, now = Date.now(), deduplicate = true): boolean {
  while (recent.length && now - recent[0].at >= 60000) recent.shift();
  for (const [key, at] of duplicates) if (now - at >= 900000) duplicates.delete(key);
  const digest = createHash('sha256').update(JSON.stringify(data)).digest('hex');
  const key = `${client}:${digest}`;
  if (recent.length >= 100 || recent.filter(r => r.client === client).length >= 5 || (deduplicate && (duplicates.has(key) || duplicates.size >= 10000))) return false;
  recent.push({ at: now, client }); if (deduplicate) duplicates.set(key, now); return true;
}

export function validateProposal(input: unknown): Record<string, string> {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Proposal must be an object');
  const limits: Record<string, number> = { name: 120, email: 254, github: 300, linkedin: 300, website: 512, track: 120, message: 4000, fax: 0 };
  const data: Record<string, string> = {};
  for (const [key, value] of Object.entries(input)) {
    if (!Object.prototype.hasOwnProperty.call(limits, key) || typeof value !== 'string' || value.length > limits[key] || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)) throw new Error('Invalid proposal field');
    if (key !== 'fax') data[key] = value.trim();
  }
  for (const key of Object.keys(limits)) if (key !== 'fax' && !data[key]) data[key] = '';
  if (!data.name || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email) || data.message.length < 10) throw new Error('Name, valid email and substantive message required');
  for (const [key, host] of [['github', 'github.com'], ['linkedin', 'linkedin.com']]) {
    const value = data[key];
    if (value.includes('://')) {
      const url = new URL(value);
      if (url.protocol !== 'https:' || ![host, `www.${host}`].includes(url.hostname) || url.username || url.password) throw new Error('Invalid profile URL');
    } else if (!/^@?[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(value)) throw new Error('Invalid profile handle');
  }
  if (data.website) { const url = new URL(data.website); if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) throw new Error('Invalid website'); }
  data.email = data.email.toLowerCase(); return data;
}
