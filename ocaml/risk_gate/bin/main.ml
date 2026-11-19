(* Line protocol driver for the shadow risk gate.

   stdin : one request per line, '|'-separated key=value pairs (see
           cryptoscope/execution/shadow_gate.py for the writer).
   stdout: one line per request:
             ALLOW|reasons=|halted=0|peak=<float>
             REJECT|reasons=CODE1,CODE2|halted=0|1|peak=<float>
             ERROR|<message>                       (malformed request; fail closed)
*)

open Gate

let kv_of_line line =
  String.split_on_char '|' line
  |> List.filter_map (fun p ->
         match String.index_opt p '=' with
         | Some i -> Some (String.sub p 0 i, String.sub p (i + 1) (String.length p - i - 1))
         | None -> None)

let get kv k =
  match List.assoc_opt k kv with Some v -> v | None -> failwith ("missing field " ^ k)

let flt s = float_of_string s
let int_ s = int_of_string s
let bool_ s = s = "1"

let float_list s =
  String.split_on_char ',' s |> List.filter (fun x -> x <> "") |> List.map flt

let str_list s =
  String.split_on_char ',' s |> List.filter (fun x -> x <> "") |> List.map String.uppercase_ascii

let parse kv =
  let cfg =
    {
      max_position_fraction = flt (get kv "cfg.max_position_fraction");
      max_open_orders = int_ (get kv "cfg.max_open_orders");
      daily_loss_limit_fraction = flt (get kv "cfg.daily_loss_limit_fraction");
      total_drawdown_limit_fraction = flt (get kv "cfg.total_drawdown_limit_fraction");
      max_trades_per_day = int_ (get kv "cfg.max_trades_per_day");
      loss_cooldown_seconds = flt (get kv "cfg.loss_cooldown_seconds");
      symbol_allowlist = str_list (get kv "cfg.symbol_allowlist");
      max_feed_age_seconds = flt (get kv "cfg.max_feed_age_seconds");
      max_divergence_pct = flt (get kv "cfg.max_divergence_pct");
    }
  in
  let st =
    {
      emergency_halted = bool_ (get kv "st.emergency_halted");
      peak_equity = flt (get kv "st.peak_equity");
      trade_timestamps = float_list (get kv "st.trade_timestamps");
      last_loss_time =
        (match get kv "st.last_loss_time" with "none" -> None | s -> Some (flt s));
    }
  in
  let token_audit =
    match List.assoc_opt "req.token_present" kv with
    | Some "1" ->
        Some { band = get kv "req.token_band"; score = flt (get kv "req.token_score") }
    | _ -> None
  in
  let req =
    {
      symbol = get kv "req.symbol";
      action = get kv "req.action";
      requested_value = flt (get kv "req.requested_value");
      total_portfolio_equity = flt (get kv "req.total_portfolio_equity");
      open_orders = int_ (get kv "req.open_orders");
      feed_age_seconds = flt (get kv "req.feed_age_seconds");
      cross_source_divergence_pct = flt (get kv "req.cross_source_divergence_pct");
      day_pnl = flt (get kv "req.day_pnl");
      day_start_equity = flt (get kv "req.day_start_equity");
      now = flt (get kv "req.now");
      token_audit;
    }
  in
  (cfg, st, req)

let render (v : verdict) =
  let codes = String.concat "," (List.map code_of_reason v.reasons) in
  Printf.sprintf "%s|reasons=%s|halted=%d|peak=%.17g"
    (if v.allowed then "ALLOW" else "REJECT")
    codes
    (if v.state_after.emergency_halted then 1 else 0)
    v.state_after.peak_equity

let () =
  try
    while true do
      let line = input_line stdin in
      if String.trim line <> "" then begin
        let out =
          try
            let cfg, st, req = parse (kv_of_line line) in
            render (decide cfg st req)
          with e -> "ERROR|" ^ Printexc.to_string e
        in
        print_endline out;
        flush stdout
      end
    done
  with End_of_file -> ()
