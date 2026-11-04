import { issueOperatorCookie, allowSubmission, matchesOperatorPasscode, sameOrigin } from '../lib/server/form-security.js';
import type { VercelRequest, VercelResponse } from '@vercel/node';

const MASTER_PASSCODE = process.env.COLLAB_DESK_PASSCODE || '';

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Cross-origin credential sharing is deliberately not enabled.
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Desk-Passcode');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  if (!sameOrigin(req.headers.origin, req.headers.host)) return res.status(403).json({ error: 'Cross-origin request refused' });
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body || {};
    const { passcode, action } = body;
    if (!allowSubmission({ action: 'operator-auth' }, req.socket.remoteAddress || 'unknown', Date.now(), false)) return res.status(429).json({ error: 'Authentication quota exceeded' });

    // Handle logout action
    if (action === 'logout') {
      res.setHeader('Set-Cookie', 'zillers_collab_auth=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax');
      return res.status(200).json({ success: true, message: 'Logged out successfully' });
    }

    if (!passcode || typeof passcode !== 'string') {
      return res.status(400).json({ error: 'Passcode is required' });
    }

    // Secure string check
    if (matchesOperatorPasscode(passcode, MASTER_PASSCODE)) {
      const isProd = process.env.NODE_ENV === 'production' || process.env.VERCEL === '1';
      const cookieStr = `zillers_collab_auth=${issueOperatorCookie(MASTER_PASSCODE)}; Path=/; Max-Age=604800; HttpOnly; SameSite=Lax${isProd ? '; Secure' : ''}`;
      res.setHeader('Set-Cookie', cookieStr);
      return res.status(200).json({
        success: true,
        message: 'Passcode verified successfully. Desk unlocked.',
      });
    }

    return res.status(401).json({ error: 'Invalid operator passcode' });
  } catch (err: any) {
    return res.status(500).json({ error: 'Authentication processing failed', details: 'Request failed' });
  }
}
