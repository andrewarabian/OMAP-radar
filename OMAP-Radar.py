#!/usr/bin/env python3
# OMAP | Offline Mesh Analysis Plotter | v1.00.01 alpha | November 18, 2025 | github.com/andrewarabian
# 

 #######  ##     ##    ###    ########     ########     ###    ########     ###    ######## 
##     ## ###   ###   ## ##   ##     ##    ##     ##   ## ##   ##     ##   ## ##   ##     ##
##     ## #### ####  ##   ##  ##     ##    ##     ##  ##   ##  ##     ##  ##   ##  ##     ##
##     ## ## ### ## ##     ## ########     ########  ##     ## ##     ## ##     ## ######## 
##     ## ##     ## ######### ##           ##   ##   ######### ##     ## ######### ##   ##  
##     ## ##     ## ##     ## ##           ##    ##  ##     ## ##     ## ##     ## ##    ## 
 #######  ##     ## ##     ## ##           ##     ## ##     ## ########  ##     ## ##     ##

#
import os, math, time, threading, queue
from datetime import datetime

import pygame
from pubsub import pub
import meshtastic, meshtastic.serial_interface
try:
    import serial.tools.list_ports as list_ports
except Exception:
    list_ports = None

# ---------- CONFIG ----------
FONT_PATH   = "TerminusTTF-4.49.3.ttf"
FONT_SIZE   = 22
FONT_SMALL  = 17
FONT_TINY   = 17
NAME_TINY   = 16

FPS                 = 20
NODEDB_POLL_SEC     = 5

RIGHT_PANEL_FRACTION= 0.36
RIGHT_PANEL_W_MIN   = 460
RIGHT_PANEL_W_MAX   = 780

MARGIN              = 48
FOOTER_H            = 118

STALE_SEC           = 300
LABEL_COUNT_DEFAULT = 8

# -------- COLORS ----------
BG_COLOR      = (5,5,5)
PANEL_BG      = (10,10,10)
GRID_THIN     = (25,25,25)
GRID_BOLD     = (42,42,42)
TEXT_DIM      = (222,222,222)
TEXT_BR       = (108,255,162)
TABLE_TEXT    = (222,222,222)

NODE_COLOR    = (30, 84, 250)
NODE_DIM      = (0, 70, 45)
NAME_UNIFORM  = (28, 255,122)

LINK_COLOR    = (10,32,136)
FLOW_DOT      = (7, 81, 97)

# ---- GRID SPACING -------
MINOR_LAT_DEG = 0.005
MINOR_LON_DEG = 0.005
MAJOR_EVERY   = 48

# ------ LINKS -----------
LINK_MODE_CYCLE = ("mst_knn", "mst", "knn")
DEFAULT_LINK_MODE = "mst_knn"
K_NEIGHBORS       = 2
LINK_MAX_METERS   = 60000

FLOW_ON        = True
FLOW_SPEED_PX_S= 120.0
FLOW_SPACING_PX= 28
FLOW_DOT_R     = 2

# target puck
TARGET_PUCK_R  = 6

# input
WASD_ACCEL     = 28400.0
WASD_FRICTION  = 7.0
ZOOM_STEP      = 1.15

# ---------- STATE ----------
q = queue.Queue()
nodes = {}
origin = {"lat": None, "lon": None, "set": False}
status = {"port": None, "connected": False, "last_polled": 0, "last_packet": 0}

# view
zoom_mode = "fit"
zoom_k    = 1.0
pan_x_m   = 0.0
pan_y_m   = 0.0
pan_vx    = 0.0
pan_vy    = 0.0
show_labels = True
hide_stale  = True
label_count = LABEL_COUNT_DEFAULT

link_mode   = DEFAULT_LINK_MODE
flow_on     = FLOW_ON
show_target = True  # TOGGLE W/ R

PORT_OVERRIDE=None

# ---------- UTIL ----------
def now(): return time.time()

def latlon_to_xy_m(lat, lon, lat0, lon0):
    if None in (lat, lon, lat0, lon0): return None
    R = 111320.0
    x = (lon - lon0) * math.cos(math.radians(lat0)) * R
    y = (lat - lat0) * R
    return x, y

def xy_m_to_latlon(xm, ym, lat0, lon0):
    R = 111320.0
    lat = lat0 + (ym / R)
    lon = lon0 + (xm / (R * math.cos(math.radians(lat0))))
    return lat, lon

def set_origin_if_empty(lat, lon):
    if lat is not None and lon is not None and not origin["set"]:
        origin.update({"lat": float(lat), "lon": float(lon), "set": True})

def upsert_node(nid, name=None, lat=None, lon=None, ts=None):
    rec = nodes.get(nid) or {"name": nid, "lat": None, "lon": None, "last": now()}
    if name: rec["name"] = name
    rec["last"] = float(ts or now())
    if lat is not None and lon is not None:
        rec["lat"], rec["lon"] = float(lat), float(lon)
        set_origin_if_empty(lat, lon)
    nodes[nid] = rec

def detect_ports():
    if PORT_OVERRIDE: return [PORT_OVERRIDE]
    cands = []
    for pat in ("/dev/ttyACM","/dev/ttyUSB","/dev/cu.usbserial","/dev/cu.SLAB_USBtoUART"):
        for i in range(8):
            p = f"{pat}{i}" if pat.endswith(("ACM","USB")) else pat
            if os.path.exists(p): cands.append(p)
    if list_ports:
        for p in list_ports.comports(): cands.append(p.device)
    out, seen = [], set()
    for p in cands:
        if p not in seen:
            seen.add(p); out.append(p)
    return out or [None]

# ---------- Meshtastic handlers (bytes-safe & silent) ----------
def _as_dict(obj):
    if isinstance(obj, dict): return obj
    if hasattr(obj, "__dict__"):
        try: return dict(obj.__dict__)
        except Exception: return None
    return None

def on_rx(packet=None, interface=None, iface=None, **_):
    status["last_packet"] = now()
    if packet is None or isinstance(packet, (bytes, bytearray)):
        return
    pkt = packet if isinstance(packet, dict) else _as_dict(packet)
    if not pkt:
        return
    try:
        if iface is None: iface = interface
        nid = pkt.get("fromId") or str(pkt.get("from") or "") or "unknown"
        ts  = float(pkt.get("rxTime") or now())

        name = None
        frm  = pkt.get("from")
        if isinstance(frm, dict):
            name = frm.get("longName") or frm.get("shortName")

        decoded = pkt.get("decoded") or {}
        pos = None
        if isinstance(decoded, dict):
            pos = decoded.get("position") or (decoded.get("payload") or {}).get("position")
        pos = pos or pkt.get("position") or (pkt.get("payload") or {}).get("position")

        if isinstance(pos, dict) and "latitude" in pos and "longitude" in pos:
            upsert_node(nid, name or nid, pos.get("latitude"), pos.get("longitude"), ts)
        else:
            upsert_node(nid, name or nid, ts=ts)

        q.put(("rx", nid, ts))
    except Exception:
        return

def on_node_updated(node=None, **_):
    nd = node if isinstance(node, dict) else _as_dict(node)
    if not nd:
        return
    try:
        nid = str(nd.get("num") or nd.get("id") or "")
        if not nid:
            return
        user = nd.get("user") or {}
        name = user.get("longName") or user.get("shortName") or nid
        pos  = nd.get("position") or {}
        upsert_node(nid, name, pos.get("latitude"), pos.get("longitude"), now())
        q.put(("node", nid, now()))
    except Exception:
        return

def iface_thread():
    ports=detect_ports(); iface=None
    for p in ports:
        try:
            print(f"[meshtastic] trying {p}")
            iface = meshtastic.serial_interface.SerialInterface(p)
            status.update({"port":p,"connected":True}); break
        except Exception as e:
            print(f"[meshtastic] {p} failed: {e}"); time.sleep(0.4)
    if not status["connected"]:
        print("[meshtastic] no port; UI will run offline.")
        return

    pub.subscribe(on_rx, "meshtastic.receive")
    pub.subscribe(on_node_updated, "meshtastic.node.updated")

    try:
        try: iface.getNodeDB()
        except Exception: pass
        while True:
            if now()-status["last_polled"]>=NODEDB_POLL_SEC:
                status["last_polled"]=now()
                try:
                    nd=iface.nodes
                    if isinstance(nd,dict):
                        for nid,data in nd.items():
                            user=data.get("user") or {}
                            name=user.get("longName") or user.get("shortName") or str(nid)
                            pos =data.get("position") or {}
                            upsert_node(str(nid), name, pos.get("latitude"), pos.get("longitude"), now())
                except Exception:
                    try: iface.getNodeDB()
                    except Exception: pass
            time.sleep(0.25)
    finally:
        try: iface.close()
        except: pass

# -------- Fonts --------
def load_fonts():
    try:
        if os.path.exists(FONT_PATH):
            f1 = pygame.font.Font(FONT_PATH,FONT_SIZE)
            f2 = pygame.font.Font(FONT_PATH,FONT_SMALL)
            f3 = pygame.font.Font(FONT_PATH,FONT_TINY)
            f4 = pygame.font.Font(FONT_PATH,NAME_TINY)
            return f1,f2,f3,f4
    except Exception:
        pass
    return (pygame.font.SysFont("monospace",FONT_SIZE),
            pygame.font.SysFont("monospace",FONT_SMALL),
            pygame.font.SysFont("monospace",FONT_TINY),
            pygame.font.SysFont("monospace",NAME_TINY))

# -------- Geometry helpers --------
def _euclid2(ax, ay, bx, by):
    dx = ax - bx; dy = ay - by
    return dx*dx + dy*dy

def build_mst_edges(points):
    n = len(points)
    if n <= 1: return []
    in_tree = [False]*n
    dist2   = [float("inf")]*n
    parent  = [-1]*n
    in_tree[0] = True
    for j in range(1, n):
        dist2[j]  = _euclid2(points[0][0], points[0][1], points[j][0], points[j][1])
        parent[j] = 0
    edges = []
    for _ in range(n-1):
        k = -1; best = float("inf")
        for j in range(n):
            if not in_tree[j] and dist2[j] < best:
                best = dist2[j]; k = j
        if k == -1: break
        in_tree[k] = True
        edges.append((k, parent[k]))
        for j in range(n):
            if not in_tree[j]:
                d2 = _euclid2(points[k][0], points[k][1], points[j][0], points[j][1])
                if d2 < dist2[j]:
                    dist2[j]  = d2
                    parent[j] = k
    return edges

def build_knn_edges(points, k=2, max_m=LINK_MAX_METERS):
    n = len(points)
    out = set()
    max_m2 = max_m*max_m
    for i in range(n):
        dlist = []
        xi, yi = points[i]
        for j in range(n):
            if i == j: continue
            d2 = _euclid2(xi, yi, points[j][0], points[j][1])
            dlist.append((d2, j))
        dlist.sort(key=lambda t: t[0])
        added = 0
        for d2, j in dlist:
            if d2 <= max_m2:
                a, b = (i, j) if i < j else (j, i)
                if (a, b) not in out:
                    out.add((a, b)); added += 1
                    if added >= k: break
    return list(out)

def build_links(points, mode):
    if len(points) <= 1: return []
    if mode == "mst":
        return build_mst_edges(points)
    if mode == "knn":
        return build_knn_edges(points)
    mst = set(tuple(sorted(e)) for e in build_mst_edges(points))
    knn = set(build_knn_edges(points))
    return list(mst | knn)

# ---------- MAIN ----------
def main():
    global zoom_mode, zoom_k, pan_x_m, pan_y_m, pan_vx, pan_vy
    global show_labels, hide_stale, label_count, link_mode, flow_on, show_target

    pygame.init()
    screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
    pygame.display.set_caption("Meshtastic — Tactical Mesh Display")
    clock = pygame.time.Clock()

    font_main, font_small, font_tiny, font_name = load_fonts()
    threading.Thread(target=iface_thread, daemon=True).start()

    dragging=False; drag_start=None; pan_start=(0,0)
    last_time=time.time()
    keys_held=set()

    side_scroll = 0
    side_content_h = 0

    WHEEL_EVT = pygame.USEREVENT+1
    PAN_EVT   = pygame.USEREVENT+2

    while True:
        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: return
            elif ev.type==pygame.KEYDOWN:
                if ev.key==pygame.K_ESCAPE: return
                if ev.key in (pygame.K_w,pygame.K_a,pygame.K_s,pygame.K_d,
                              pygame.K_UP,pygame.K_DOWN,pygame.K_LEFT,pygame.K_RIGHT):
                    keys_held.add(ev.key)
                elif ev.key==pygame.K_l: show_labels=not show_labels
                elif ev.key==pygame.K_f: hide_stale=not hide_stale
                elif ev.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    zoom_mode="manual"; zoom_k*=ZOOM_STEP
                elif ev.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                    zoom_mode="manual"; zoom_k/=ZOOM_STEP
                elif ev.key==pygame.K_0:
                    zoom_mode="fit"; zoom_k=1.0
                    pan_x_m=pan_y_m=0.0; pan_vx=pan_vy=0.0
                elif ev.key==pygame.K_r:
                    show_target = not show_target
                elif ev.key==pygame.K_e and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    flow_on = not flow_on
                elif ev.key==pygame.K_e:
                    i = LINK_MODE_CYCLE.index(link_mode)
                    link_mode = LINK_MODE_CYCLE[(i+1)%len(LINK_MODE_CYCLE)]
                elif ev.key==pygame.K_PAGEUP:
                    side_scroll = max(0, side_scroll - 500)
                elif ev.key==pygame.K_PAGEDOWN:
                    side_scroll += 500
                elif ev.key==pygame.K_HOME:
                    side_scroll = 0
                elif ev.key==pygame.K_END:
                    side_scroll = 10**9
            elif ev.type==pygame.KEYUP:
                if ev.key in keys_held: keys_held.discard(ev.key)
            elif ev.type==pygame.MOUSEBUTTONDOWN:
                if ev.button==1:
                    dragging=True; drag_start=ev.pos; pan_start=(pan_x_m, pan_y_m)
                elif ev.button in (4,5):
                    pygame.event.post(pygame.event.Event(WHEEL_EVT, dict(pos=ev.pos, dir=1 if ev.button==4 else -1)))
            elif ev.type==pygame.MOUSEBUTTONUP and ev.button==1:
                dragging=False
            elif ev.type==pygame.MOUSEMOTION and dragging:
                dx,dy = ev.pos[0]-drag_start[0], ev.pos[1]-drag_start[1]
                pygame.event.post(pygame.event.Event(PAN_EVT, dict(pix_pan=(dx,dy), pan_start=pan_start)))
            elif ev.type==pygame.MOUSEWHEEL:
                mx,my = pygame.mouse.get_pos()
                pygame.event.post(pygame.event.Event(WHEEL_EVT, dict(pos=(mx,my), dir=1 if ev.y>0 else -1)))

        try:
            while True: q.get_nowait()
        except queue.Empty:
            pass

        t=time.time(); dt=max(1e-3, t-last_time); last_time=t

        # ---- sizing
        W,H = screen.get_size()
        right_w = max(RIGHT_PANEL_W_MIN, min(RIGHT_PANEL_W_MAX, int(W*RIGHT_PANEL_FRACTION)))
        plot = pygame.Rect(MARGIN, MARGIN+40, W-right_w-2*MARGIN, H-(MARGIN+FOOTER_H))
        side = pygame.Rect(plot.right+14, MARGIN+40, right_w-20, H-(MARGIN+FOOTER_H+12))

        # bg + frames/panels
        screen.fill(BG_COLOR)
        pygame.draw.rect(screen, PANEL_BG, side)
        pygame.draw.rect(screen, (5,5,5), side, 1)
        pygame.draw.rect(screen, (40,40,40), plot, 1)

        _now=now()
        # Top left meta
        hdr = "Origin: " + (f"{origin['lat']:.5f}, {origin['lon']:.5f}" if origin["set"] else "awaiting first position…")
        screen.blit(font_main.render(hdr, True, TEXT_BR), (10, 8))
        meta=f"Nodes heard: {len(nodes)}    Port: {status['port'] or 'auto'}    Connected: {status['connected']}    Last pkt: {int(_now-status['last_packet']) if status['last_packet'] else '—'}s"
        screen.blit(font_small.render(meta, True, TEXT_DIM), (10, 28))

        cx=plot.centerx; cy=plot.centery

        # nodes → plottable
        plottable=[]
        if origin["set"]:
            lat0, lon0 = origin["lat"], origin["lon"]
            for nid,d in nodes.items():
                if d["lat"] is not None and d["lon"] is not None:
                    xy=latlon_to_xy_m(d["lat"],d["lon"],lat0,lon0)
                    if xy:
                        age=_now-d["last"]
                        if not hide_stale or age<=STALE_SEC:
                            plottable.append((nid, d["name"], xy[0], xy[1], age))
        plottable.sort(key=lambda p: p[4])
        screen.blit(font_small.render(f"Plottable: {len(plottable)}", True, TEXT_DIM), (10, 46))

        # scale
        far=200.0
        for _,_,xm,ym,_ in plottable:
            far=max(far, math.hypot(xm,ym))
        max_px_radius=int(min(plot.width, plot.height)*0.46)
        fit_scale = max_px_radius/far if far>0 else 1.0
        scale = fit_scale if zoom_mode=="fit" else max(0.0001, fit_scale*zoom_k)

        def to_screen(xm,ym):
            return int(cx+(xm-pan_x_m)*scale), int(cy-(ym-pan_y_m)*scale)

        # wheel/drag updates
        for ev in pygame.event.get([WHEEL_EVT, PAN_EVT]):
            if ev.type==WHEEL_EVT:
                mx,my = ev.pos; dirn = ev.dir
                if side.collidepoint(mx, my):
                    step = (FONT_SMALL+6)*4
                    side_scroll -= dirn * step
                else:
                    wx = (mx - cx)/scale + pan_x_m
                    wy = -(my - cy)/scale + pan_y_m
                    zoom_mode="manual"
                    zoom_k *= (ZOOM_STEP if dirn>0 else 1.0/ZOOM_STEP)
                    scale = fit_scale if zoom_mode=="fit" else max(0.0001, fit_scale*zoom_k)
                    pan_x_m = wx - (mx - cx)/scale
                    pan_y_m = wy + (my - cy)/scale
            else:
                dx,dy = ev.pix_pan
                pan_x_m = ev.pan_start[0] - dx/scale
                pan_y_m = ev.pan_start[1] + dy/scale

        # WASD smooth motion
        accel = WASD_ACCEL / max(0.5, zoom_k)
        a_x = ((pygame.K_d in keys_held) or (pygame.K_RIGHT in keys_held)) - ((pygame.K_a in keys_held) or (pygame.K_LEFT in keys_held))
        a_y = ((pygame.K_w in keys_held) or (pygame.K_UP in keys_held)) - ((pygame.K_s in keys_held) or (pygame.K_DOWN in keys_held))
        pan_vx += a_x * accel * dt
        pan_vy += a_y * accel * dt
        pan_vx *= max(0.0, 1.0 - WASD_FRICTION*dt)
        pan_vy *= max(0.0, 1.0 - WASD_FRICTION*dt)
        pan_x_m += pan_vx * dt
        pan_y_m += pan_vy * dt

        # ----- DRAW PLOT -----
        screen.set_clip(plot)

        if origin["set"]:
            def draw_geo_grid(rect):
                """Draw grid lines, then draw major tick labels on top with an underlay."""
                R = 111320.0

                # View window in meters relative to plot center
                left_m  = (rect.left  - rect.centerx)/scale + pan_x_m
                right_m = (rect.right - rect.centerx)/scale + pan_x_m
                top_m   = (rect.centery - rect.top)/scale + pan_y_m
                bot_m   = (rect.centery - rect.bottom)/scale + pan_y_m

                # Convert to lat/lon bounds
                lat_top,  lon_left  = xy_m_to_latlon(left_m,  top_m,  origin["lat"], origin["lon"])
                lat_bot,  lon_right = xy_m_to_latlon(right_m, bot_m, origin["lat"], origin["lon"])
                lat_min = min(lat_top, lat_bot); lat_max = max(lat_top, lat_bot)
                lon_min = min(lon_left, lon_right); lon_max = max(lon_left, lon_right)

                def round_down(v, step): return math.floor(v/step)*step

                # First pass: draw all grid lines and collect positions for majors
                major_lon_labels = []  # (x, text)
                major_lat_labels = []  # (y, text)

                # vertical (longitude) lines
                lon = round_down(lon_min, MINOR_LON_DEG); idx = 0
                while lon <= lon_max + 1e-9:
                    x_m = (lon - origin["lon"]) * math.cos(math.radians(origin["lat"])) * R
                    x   = int(rect.centerx + (x_m - pan_x_m)*scale)
                    pygame.draw.line(screen, GRID_BOLD if (idx % MAJOR_EVERY==0) else GRID_THIN, (x, rect.top), (x, rect.bottom), 1)
                    if idx % MAJOR_EVERY == 0:
                        major_lon_labels.append((x+4, f"{lon:.5f}°"))
                    lon += MINOR_LON_DEG; idx += 1

                # horizontal (latitude) lines
                lat = round_down(lat_min, MINOR_LAT_DEG); idx = 0
                while lat <= lat_max + 1e-9:
                    y_m = (lat - origin["lat"]) * R
                    y   = int(rect.centery - (y_m - pan_y_m)*scale)
                    pygame.draw.line(screen, GRID_BOLD if (idx % MAJOR_EVERY==0) else GRID_THIN, (rect.left, y), (rect.right, y), 1)
                    if idx % MAJOR_EVERY == 0:
                        major_lat_labels.append((y+2, f"{lat:.5f}°"))
                    lat += MINOR_LAT_DEG; idx += 1

                # Second pass: render labels ABOVE grid with a subtle background
                def blit_with_underlay(surf, x, y, pad=3):
                    under = pygame.Surface((surf.get_width()+2*pad, surf.get_height()+2*pad), pygame.SRCALPHA)
                    under.fill((0,0,0,140))
                    screen.blit(under, (x-pad, y-pad))
                    screen.blit(surf, (x, y))

                for x, text in major_lon_labels:
                    ts = font_tiny.render(text, True, TEXT_DIM)
                    blit_with_underlay(ts, x, rect.top+4)

                for y, text in major_lat_labels:
                    ts = font_tiny.render(text, True, TEXT_DIM)
                    blit_with_underlay(ts, rect.left+6, y)

            draw_geo_grid(plot)

        if origin["set"] and show_target:
            pygame.draw.circle(screen, (200,220,220), (plot.centerx, plot.centery), TARGET_PUCK_R, 1)
            if fit_scale>0 and (scale/fit_scale) >= 1.6:
                lat_t, lon_t = xy_m_to_latlon(pan_x_m, pan_y_m, origin["lat"], origin["lon"])
                coord_txt = f"{lat_t:.5f}, {lon_t:.5f}"
                surf = font_tiny.render(coord_txt, True, (190,210,200))
                pad = 4
                under = pygame.Surface((surf.get_width()+2*pad, surf.get_height()+2*pad), pygame.SRCALPHA)
                under.fill((0,0,0,110))
                tx = plot.centerx - surf.get_width() - 14
                ty = plot.centery + 10
                screen.blit(under, (tx-pad, ty-pad))
                screen.blit(surf, (tx, ty))

        mapped = [(nid,name,xm,ym,age) for (nid,name,xm,ym,age) in plottable]
        points_m = [(xm, ym) for (_,_,xm,ym,_) in mapped]
        edges = build_links(points_m, link_mode)
        points_px= [to_screen(xm,ym) for (xm,ym) in points_m]
        for i, j in edges:
            x1,y1 = points_px[i]; x2,y2 = points_px[j]
            pygame.draw.line(screen, (LINK_COLOR), (x1,y1), (x2,y2), 1)
        if flow_on:
            phase = (t * FLOW_SPEED_PX_S) % FLOW_SPACING_PX
            for i, j in edges:
                x1,y1 = points_px[i]; x2,y2 = points_px[j]
                dx,dy = x2-x1, y2-y1
                L = math.hypot(dx,dy)
                if L < 1: continue
                nx,ny = dx/L, dy/L
                s = phase
                while s < L:
                    cxp = int(x1 + nx*s); cyp = int(y1 + ny*s)
                    pygame.draw.circle(screen, (FLOW_DOT), (cxp,cyp), FLOW_DOT_R)
                    s += FLOW_SPACING_PX

        for _,name,xm,ym,age in mapped:
            px,py = to_screen(xm,ym)
            dot_col = NODE_COLOR if age<STALE_SEC else NODE_DIM
            pygame.draw.circle(screen, dot_col, (px,py), 5 if age<STALE_SEC else 3)
            if show_labels:
                screen.blit(font_name.render(name, True, NAME_UNIFORM), (px+8, py-8))

        screen.set_clip(None)  

        # -------- Right panel (scrollable) --------
        screen.set_clip(side)

        y0_visible = side.top+8
        y = y0_visible - side_scroll
        x = side.left+10
        w = side.width-20
        fontH = font_small.get_height()

        def header(text):
            nonlocal y
            if y + fontH > side.top-40 and y < side.bottom:
                screen.blit(font_main.render(text, True, (200,200,210)), (x,y))
                pygame.draw.line(screen,(NAME_UNIFORM),(x,y+fontH+6),(x+w,y+fontH+6),1)
            y += fontH+12

        def zebra_row(i, rect):
            if i%2==1:
                r=pygame.Rect(rect)
                r.top = max(r.top, side.top)
                r.bottom = min(r.bottom, side.bottom)
                if r.height>0:
                    pygame.draw.rect(screen, (5,5,5), r)

        def row(cols, widths, irow, ytop):
            cx_=x
            h = fontH + 6
            if ytop+h < side.top or ytop > side.bottom:
                return h
            zebra_row(irow, (x, ytop-2, w, h))
            for i,t in enumerate(cols):
                s=t
                while font_small.size(s)[0]>widths[i] and len(s)>3: s=s[:-4]+"…"
                screen.blit(font_small.render(s,True,(TABLE_TEXT)), (cx_, ytop))
                cx_+=widths[i]
            pygame.draw.line(screen, (PANEL_BG), (x, ytop+h-2), (x+w, ytop+h-2), 1)
            return h

        # Only POS table (messages removed)
        _now=now()
        mapped_rows=[]
        if origin["set"]:
            for d in nodes.values():
                if d["lat"] is None or d["lon"] is None: continue
                xy=latlon_to_xy_m(d["lat"],d["lon"],origin["lat"],origin["lon"])
                if xy:
                    rng=math.hypot(xy[0],xy[1]); age=_now-d["last"]; mapped_rows.append((d["name"],rng,age))
        mapped_rows.sort(key=lambda r:(r[1],r[2]))
        header(f"Mapped (POS) [{len(mapped_rows)}]")
        name_w2=max(260,w-160); widths=[name_w2,70,70]
        y+=row(["Name","Rng","Age"], widths, 0, y)
        irow=1
        for nm,rng,age in mapped_rows:
            y+=row([nm, f"{int(rng)}m", f"{int(age)}s"], widths, irow, y)
            irow+=1

        # ALL nodes
        all_rows=[]
        for d in nodes.values():
            haspos=(d["lat"] is not None and d["lon"] is not None)
            rng="-"
            if haspos and origin["set"]:
                xm,ym=latlon_to_xy_m(d["lat"],d["lon"],origin["lat"],origin["lon"])
                rng=f"{int(math.hypot(xm,ym))}m"
            all_rows.append((d["name"], rng, _now-d["last"]))
        all_rows.sort(key=lambda r:(r[2], r[0].lower()))
        y += 12
        header(f"All [{len(nodes)}]")
        y+=row(["Name","Rng","Age"], widths, 0, y)
        irow=1
        for nm,rng,age in all_rows:
            y+=row([nm, rng, f"{int(age)}s"], widths, irow, y)
            irow+=1

        side_content_h = y - y0_visible
        max_scroll = max(0, side_content_h - side.height + 8)
        if side_scroll > max_scroll: side_scroll = max_scroll
        if side_scroll < 0: side_scroll = 0

        # slim scrollbar
        if max_scroll > 0:
            bar = pygame.Rect(side.right-6, side.top+2, 4, side.height-4)
            pygame.draw.rect(screen, (40,40,40), bar, border_radius=2)
            frac = (side_scroll / max_scroll) if max_scroll else 0
            knob_h = max(24, int((side.height-4) * min(1.0, (side.height-8)/ (side_content_h+1e-9))))
            knob_y = side.top+2 + int((side.height-4 - knob_h) * frac)
            pygame.draw.rect(screen, (70,76,92), (side.right-6, knob_y, 4, knob_h), border_radius=2)

        screen.set_clip(None)  

        # -------- Footer --------
        footer = pygame.Rect(0, screen.get_height()-FOOTER_H, screen.get_width(), FOOTER_H)
        pygame.draw.rect(screen, PANEL_BG, footer)
        pygame.draw.line(screen,(NAME_UNIFORM),(0,footer.top),(screen.get_width(),footer.top),1)

        hints1 = "WASD/Arrows: pan (smooth)   Mouse wheel: zoom at cursor   Left-drag: pan   +/-/0: zoom fit   R: toggle target"
        hints2 = f"L: labels   F: hide stale [{'ON' if hide_stale else 'OFF'}]   E: link mode ({link_mode})   Shift+E: flow   PgUp/PgDn/Home/End: scroll panel   ESC: quit"
        screen.blit(font_small.render(hints1, True, TEXT_DIM), (MARGIN+8, footer.top+10))
        screen.blit(font_small.render(hints2, True, TEXT_DIM), (MARGIN+8, footer.top+32))

        pygame.display.flip()
        clock.tick(FPS)

if __name__=="__main__":
    main()
