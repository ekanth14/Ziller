import type { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

const MASTER_PASSCODE = process.env.COLLAB_DESK_PASSCODE || 'Ekanthbs@4514';
const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY || '';

// Fallback in-memory proposals store for environments without Supabase configured yet
const memoryProposals: Array<Record<string, any>> = [];

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
  if (typeof headerCode === 'string' && headerCode.trim() === MASTER_PASSCODE) {
    return true;
  }
  const cookies = parseCookies(req.headers.cookie);
  if (cookies['zillers_collab_auth'] === MASTER_PASSCODE) {
    return true;
  }
  return false;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Desk-Passcode');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // 1. POST: Public proposal submission (open to all visitors)
  if (req.method === 'POST') {
    try {
      const data = typeof req.body === 'string' ? JSON.parse(req.body) : req.body || {};
      const { name, email, github, linkedin, website, track, message } = data;

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
        client_ip: (req.headers['x-forwarded-for'] as string) || req.socket.remoteAddress || 'unknown',
      };

      const supabase = getSupabase();
      if (supabase) {
        const { error } = await supabase.from('collaborations').insert([record]);
        if (error) {
          console.error('Supabase insertion error:', error);
          memoryProposals.unshift(record);
        }
      } else {
        memoryProposals.unshift(record);
      }

      return res.status(200).json({
        collab_id: collabId,
        message: 'Collaboration proposal successfully registered. The ZILLERS research team will reach out via email.',
        record,
      });
    } catch (err: any) {
      console.error('Error handling proposal POST:', err);
      return res.status(500).json({ error: 'Failed to process collaboration proposal', details: err?.message });
    }
  }

  // 2. GET: Retrieve proposals (PROTECTED by passcode 'Ekanthbs@4514')
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
          console.warn('Supabase fetch returned error or empty, using memory records:', error);
          records = memoryProposals;
        }
      } else {
        records = memoryProposals;
      }

      return res.status(200).json({
        status: 'ok',
        total: records.length,
        proposals: records,
        storage: supabase ? 'supabase-cloud' : 'in-memory-fallback',
      });
    } catch (err: any) {
      console.error('Error handling proposal GET:', err);
      return res.status(500).json({ error: 'Failed to retrieve collaboration proposals', details: err?.message });
    }
  }

  return res.status(405).json({ error: 'Method Not Allowed' });
}
