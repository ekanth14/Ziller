(* Pure pre-trade risk decision function.

   Mirrors cryptoscope/execution/governor.py RiskGovernor.check_pre_trade
   (checks 1-11, same order). It is a shadow checker: it never trades and never
   replaces the Python governor. Reasons are typed variants, so adding or removing
   a rule forces every match below to be updated by the compiler.

   Equivalence is on reason CODES (the token before ':' in the Python messages),
   the allow/reject verdict, and the resulting halt flag / peak equity. *)

type config = {
  max_position_fraction : float;
  max_open_orders : int;
  daily_loss_limit_fraction : float;
  total_drawdown_limit_fraction : float;
  max_trades_per_day : int;
  loss_cooldown_seconds : float;
  symbol_allowlist : string list; (* already upper-cased; [] = no restriction *)
  max_feed_age_seconds : float;
  max_divergence_pct : float;
}

type state = {
  emergency_halted : bool;
  peak_equity : float;
  trade_timestamps : float list;
  last_loss_time : float option;
}

type token_audit = { band : string; score : float }

type request = {
  symbol : string;
  action : string;
  requested_value : float;
  total_portfolio_equity : float;
  open_orders : int;
  feed_age_seconds : float;
  cross_source_divergence_pct : float;
  day_pnl : float;
  day_start_equity : float;
  now : float;
  token_audit : token_audit option;
}

type reason =
  | Emergency_halt_active
  | Stale_feed
  | Price_divergence
  | Symbol_not_allowed
  | Loss_cooldown_active
  | Max_daily_trades_exceeded
  | Total_drawdown_halt
  | Daily_loss_limit_halt
  | Invalid_action
  | Position_limit_exceeded
  | Max_orders_exceeded
  | Onchain_safety_fail

let code_of_reason = function
  | Emergency_halt_active -> "EMERGENCY_HALT_ACTIVE"
  | Stale_feed -> "STALE_FEED"
  | Price_divergence -> "PRICE_DIVERGENCE"
  | Symbol_not_allowed -> "SYMBOL_NOT_ALLOWED"
  | Loss_cooldown_active -> "LOSS_COOLDOWN_ACTIVE"
  | Max_daily_trades_exceeded -> "MAX_DAILY_TRADES_EXCEEDED"
  | Total_drawdown_halt -> "TOTAL_DRAWDOWN_HALT"
  | Daily_loss_limit_halt -> "DAILY_LOSS_LIMIT_HALT"
  | Invalid_action -> "INVALID_ACTION"
  | Position_limit_exceeded -> "POSITION_LIMIT_EXCEEDED"
  | Max_orders_exceeded -> "MAX_ORDERS_EXCEEDED"
  | Onchain_safety_fail -> "ONCHAIN_SAFETY_FAIL"

type verdict = { allowed : bool; reasons : reason list; state_after : state }

let is_entry action = action = "LONG" || action = "BUY"
let is_valid_action action =
  action = "LONG" || action = "BUY" || action = "CLOSE" || action = "SELL"

let decide (cfg : config) (st : state) (req : request) : verdict =
  if st.emergency_halted then
    { allowed = false; reasons = [ Emergency_halt_active ]; state_after = st }
  else begin
    (* peak equity is updated before any check *)
    let peak =
      if req.total_portfolio_equity > st.peak_equity then req.total_portfolio_equity
      else st.peak_equity
    in
    let halted = ref false in
    let acc = ref [] in
    let add r = acc := r :: !acc in
    (* 1. stale feed *)
    if req.feed_age_seconds > cfg.max_feed_age_seconds then add Stale_feed;
    (* 2. cross-feed divergence *)
    if req.cross_source_divergence_pct > cfg.max_divergence_pct then add Price_divergence;
    (* 3. symbol allowlist *)
    if cfg.symbol_allowlist <> []
       && not (List.mem (String.uppercase_ascii req.symbol) cfg.symbol_allowlist)
    then add Symbol_not_allowed;
    (* 4. post-loss cooldown *)
    (match st.last_loss_time with
     | Some t when req.now -. t < cfg.loss_cooldown_seconds -> add Loss_cooldown_active
     | _ -> ());
    (* 5. trades per rolling 24h *)
    let recent =
      List.length (List.filter (fun t -> t > req.now -. 86400.0) st.trade_timestamps)
    in
    if recent >= cfg.max_trades_per_day then add Max_daily_trades_exceeded;
    (* 6. total drawdown from peak (halts) *)
    if peak > 0.0 then begin
      let dd = (peak -. req.total_portfolio_equity) /. peak in
      if dd >= cfg.total_drawdown_limit_fraction then begin
        halted := true;
        add Total_drawdown_halt
      end
    end;
    (* 7. daily loss limit (halts) *)
    if req.day_start_equity > 0.0 then begin
      let loss_pct = -.req.day_pnl /. req.day_start_equity in
      if loss_pct >= cfg.daily_loss_limit_fraction then begin
        halted := true;
        add Daily_loss_limit_halt
      end
    end;
    (* 8. spot only: no shorting *)
    if not (is_valid_action req.action) then add Invalid_action;
    (* 9. position size cap on entries *)
    if req.total_portfolio_equity > 0.0 && is_entry req.action then begin
      let max_allowed = req.total_portfolio_equity *. cfg.max_position_fraction in
      if req.requested_value > max_allowed then add Position_limit_exceeded
    end;
    (* 10. max open orders *)
    if req.open_orders >= cfg.max_open_orders then add Max_orders_exceeded;
    (* 11. on-chain token safety *)
    (match req.token_audit with
     | Some ta when ta.band = "DANGER" || ta.score < 65.0 -> add Onchain_safety_fail
     | _ -> ());
    let reasons = List.rev !acc in
    {
      allowed = reasons = [];
      reasons;
      state_after =
        { st with emergency_halted = st.emergency_halted || !halted; peak_equity = peak };
    }
  end
