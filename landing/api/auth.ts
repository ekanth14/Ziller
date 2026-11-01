import type { VercelRequest, VercelResponse } from '@vercel/node';

const MASTER_PASSCODE = process.env.COLLAB_DESK_PASSCODE || 'Ekanthbs@4514';

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Desk-Passcode');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body || {};
    const { passcode, action } = body;

    // Handle logout action
    if (action === 'logout') {
      res.setHeader('Set-Cookie', 'zillers_collab_auth=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax');
      return res.status(200).json({ success: true, message: 'Logged out successfully' });
    }

    if (!passcode || typeof passcode !== 'string') {
      return res.status(400).json({ error: 'Passcode is required' });
    }

    // Secure string check
    if (passcode.trim() === MASTER_PASSCODE) {
      const isProd = process.env.NODE_ENV === 'production' || process.env.VERCEL === '1';
      const cookieStr = `zillers_collab_auth=${MASTER_PASSCODE}; Path=/; Max-Age=604800; HttpOnly; SameSite=Lax${isProd ? '; Secure' : ''}`;
      res.setHeader('Set-Cookie', cookieStr);
      return res.status(200).json({
        success: true,
        message: 'Passcode verified successfully. Desk unlocked.',
      });
    }

    return res.status(401).json({ error: 'Invalid operator passcode' });
  } catch (err: any) {
    return res.status(500).json({ error: 'Authentication processing failed', details: err?.message });
  }
}
