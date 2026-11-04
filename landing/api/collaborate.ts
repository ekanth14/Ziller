import { verifyOperatorCookie, allowSubmission, validateProposal, matchesOperatorPasscode, sameOrigin } from '../lib/server/form-security.js';
import type { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

const MASTER_PASSCODE = process.env.COLLAB_DESK_PASSCODE || '';
const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

function getSupabase() {
  if (SUPABASE_URL && SUPABASE_KEY) {
    return createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: { persistSession: false },
    });
  }
  return null;
}

function parseCookies(cookieHeader: string | undefined): Record<string, string> {
  const list: Record<string, string> = {};
  if (!cookieHeader) return list;
  cookieHeader.split(';').forEach((cookie) => {
    const parts = cookie.split('=');
    if (parts.length >= 2) {
      list[parts[0].trim()] = decodeURIComponent(parts.slice(1).join('=').trim());
    }
  });
  return list;
}

function isAuthorized(req: VercelRequest): boolean {
  const headerCode = req.headers['x-desk-passcode'];
  if (matchesOperatorPasscode(headerCode, MASTER_PASSCODE)) {
    return true;
  }
  const cookies = parseCookies(req.headers.cookie);
  if (verifyOperatorCookie(cookies['zillers_collab_auth'], MASTER_PASSCODE)) {
    return true;
  }
  return false;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Cross-origin credential sharing is deliberately not enabled.
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Desk-Passcode');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // 1. POST: Public proposal submission (open to all visitors)
  if (req.method === 'POST') {
    if (!sameOrigin(req.headers.origin, req.headers.host)) return res.status(403).json({ error: 'Cross-origin request refused' });
    if (Buffer.byteLength(JSON.stringify(req.body ?? '')) > 16384) return res.status(413).json({ error: 'Proposal too large' });
    try {
      const data = typeof req.body === 'string' ? JSON.parse(req.body) : req.body || {};
      const { name, email, github, linkedin, website, track, message } = validateProposal(data);
      const client = req.socket.remoteAddress || 'unknown';
      if (!allowSubmission(data, client)) return res.status(429).json({ error: 'Submission quota exceeded' });

      if (!name || !email || !github || !track || !message) {
        return res.status(400).json({ error: 'Missing required fields (name, email, github, track, message)' });
      }

      const collabId = `COL-${Math.random().toString(16).substring(2, 10).toUpperCase()}`;
      const record = {
        id: collabId,
        timestamp: new Date().toISOString(),
        name: String(name).trim(),
        email: String(email).trim().toLowerCase(),
        github: String(github).trim(),
        linkedin: linkedin ? String(linkedin).trim() : '',
        website: website ? String(website).trim() : '',
        track: String(track).trim(),
        message: String(message).trim(),
        client_ip: client,
      };

      const supabase = getSupabase();
      if (supabase) {
        const { error } = await supabase.from('collaborations').insert([record]);
        if (error) {
          console.error('Proposal storage failed');
          return res.status(503).json({ error: 'Proposal storage unavailable; request was not stored' });
        }
      } else {
        return res.status(503).json({ error: 'Proposal storage is not configured' });
      }

      return res.status(200).json({
        collab_id: collabId,
        message: 'Collaboration proposal successfully registered. The ZILLERS research team will reach out via email.',
        record,
      });
    } catch (err: any) {
      console.error('Proposal request failed');
      return res.status(400).json({ error: 'Failed to process collaboration proposal', details: 'Request failed' });
    }
  }

  // 2. GET: Retrieve proposals with operator authentication.
  if (req.method === 'GET') {
    if (!isAuthorized(req)) {
      return res.status(401).json({
        error: 'Passcode required to view collaboration submissions',
        help: 'Provide the verified operator passcode via header X-Desk-Passcode or authenticate at /collaborations',
      });
    }

    try {
      const supabase = getSupabase();
      let records: Array<Record<string, any>> = [];

      if (supabase) {
        const { data, error } = await supabase
          .from('collaborations')
          .select('*')
          .order('timestamp', { ascending: false });

        if (!error && Array.isArray(data)) {
          records = data;
        } else {
          console.warn('Proposal storage unavailable');
          return res.status(503).json({ error: 'Proposal storage unavailable' });
        }
      } else {
        return res.status(503).json({ error: 'Proposal storage is not configured' });
      }

      return res.status(200).json({
        status: 'ok',
        total: records.length,
        proposals: records,
        storage: 'supabase-cloud',
      });
    } catch (err: any) {
      console.error('Proposal read failed');
      return res.status(500).json({ error: 'Failed to retrieve collaboration proposals', details: 'Request failed' });
    }
  }

  return res.status(405).json({ error: 'Method Not Allowed' });
}
