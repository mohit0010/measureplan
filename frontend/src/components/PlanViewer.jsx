import React, { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Minus, RotateCcw, Layers } from "lucide-react";
import { Button } from "./ui/button";
import { ANALYSIS } from "../constants/testIds";

/**
 * PlanViewer — floor plan with SVG overlays, zoom/pan, layers, tooltips.
 * Extended:
 *   - editMode + onObjectChange(obj)  → drag body / drag corners / drag wall points
 *   - calibrateMode + onCalibrate(p1,p2)  → click two points to define a scale segment
 */
const LAYER_TYPES = {
  walls: ["wall_external", "wall_internal"],
  doors: ["door"],
  windows: ["window"],
  rooms: ["room", "bathroom"],
};

const PlanViewer = ({
  image,
  width = 1000,
  height = 700,
  objects = [],
  onSelect,
  selectedId,
  editMode = false,
  onObjectChange,
  calibrateMode = false,
  onCalibrate,
}) => {
  const wrapRef = useRef(null);
  const svgRef = useRef(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [panDrag, setPanDrag] = useState(null);
  const [objDrag, setObjDrag] = useState(null);
  const [hover, setHover] = useState(null);
  const [layers, setLayers] = useState({
    walls: true,
    doors: true,
    windows: true,
    rooms: true,
  });
  const [calibPts, setCalibPts] = useState([]);
  const [mousePt, setMousePt] = useState(null); // normalized, for calibration preview

  const visible = useMemo(
    () =>
      objects.filter((o) => {
        for (const [layer, types] of Object.entries(LAYER_TYPES)) {
          if (types.includes(o.type)) return layers[layer];
        }
        return true;
      }),
    [objects, layers]
  );

  const zoomIn = () => setZoom((z) => Math.min(4, +(z + 0.25).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)));
  const reset = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  };

  const onWheel = (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.1 : -0.1;
    setZoom((z) => Math.max(0.25, Math.min(4, +(z + delta).toFixed(2))));
  };

  useEffect(() => {
    const w = wrapRef.current;
    if (!w) return;
    w.addEventListener("wheel", onWheel, { passive: false });
    return () => w.removeEventListener("wheel", onWheel);
  }, []);

  // Reset calibration points when leaving mode
  useEffect(() => {
    if (!calibrateMode) {
      setCalibPts([]);
      setMousePt(null);
    }
  }, [calibrateMode]);

  // Fit-to-container aspect calculation
  const [box, setBox] = useState({ w: 900, h: 600 });
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      const aspect = width / height || 1.4;
      const w = r.width;
      const h = Math.min(r.height, w / aspect);
      setBox({ w, h });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [width, height]);

  const displayAspect = width / height || 1.4;
  const svgW = box.w;
  const svgH = box.w / displayAspect;

  // client → normalized
  const clientToNorm = (clientX, clientY) => {
    const el = svgRef.current;
    if (!el) return [0, 0];
    const r = el.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (clientX - r.left) / r.width)),
      Math.max(0, Math.min(1, (clientY - r.top) / r.height)),
    ];
  };
  const clientDeltaToNorm = (dxPx, dyPx) => {
    const el = svgRef.current;
    if (!el) return [0, 0];
    const r = el.getBoundingClientRect();
    return [dxPx / r.width, dyPx / r.height];
  };

  // ------ Pan / global mouse handlers ------
  const onCanvasMouseDown = (e) => {
    if (e.button !== 0) return;
    if (calibrateMode) {
      const [nx, ny] = clientToNorm(e.clientX, e.clientY);
      const next = [...calibPts, [nx, ny]];
      setCalibPts(next);
      if (next.length === 2 && onCalibrate) {
        onCalibrate(next[0], next[1]);
      }
      return;
    }
    setPanDrag({
      sx: e.clientX,
      sy: e.clientY,
      ox: offset.x,
      oy: offset.y,
    });
  };
  const onCanvasMouseMove = (e) => {
    if (objDrag) return handleObjMove(e);
    if (calibrateMode && calibPts.length === 1) {
      setMousePt(clientToNorm(e.clientX, e.clientY));
      return;
    }
    if (panDrag) {
      setOffset({
        x: panDrag.ox + (e.clientX - panDrag.sx),
        y: panDrag.oy + (e.clientY - panDrag.sy),
      });
    }
  };
  const onCanvasMouseUp = () => {
    setPanDrag(null);
    setObjDrag(null);
  };
  const onCanvasLeave = () => {
    onCanvasMouseUp();
    setHover(null);
  };

  // ------ Object drag handlers ------
  const clamp01 = (v) => Math.max(0, Math.min(1, v));

  const beginObjDrag = (e, obj, kind) => {
    if (!editMode) return;
    e.stopPropagation();
    e.preventDefault();
    onSelect && onSelect(obj);
    setObjDrag({
      objId: obj.id,
      kind,
      startX: e.clientX,
      startY: e.clientY,
      snap: JSON.parse(JSON.stringify(obj)),
    });
  };
  const handleObjMove = (e) => {
    const [dx, dy] = clientDeltaToNorm(
      e.clientX - objDrag.startX,
      e.clientY - objDrag.startY
    );
    const snap = objDrag.snap;
    let next = null;
    if (objDrag.kind === "move") {
      if (snap.points && snap.points.length) {
        next = {
          ...snap,
          x: clamp01(snap.x + dx),
          y: clamp01(snap.y + dy),
          points: snap.points.map((p) => [clamp01(p[0] + dx), clamp01(p[1] + dy)]),
        };
      } else {
        next = { ...snap, x: clamp01(snap.x + dx), y: clamp01(snap.y + dy) };
      }
    } else if (objDrag.kind.startsWith("corner-")) {
      const corner = objDrag.kind.slice("corner-".length);
      let { x, y, w, h } = snap;
      if (corner.includes("r")) w = snap.w + dx;
      if (corner.includes("l")) {
        x = snap.x + dx;
        w = snap.w - dx;
      }
      if (corner.includes("b")) h = snap.h + dy;
      if (corner.includes("t")) {
        y = snap.y + dy;
        h = snap.h - dy;
      }
      next = {
        ...snap,
        x: clamp01(x),
        y: clamp01(y),
        w: Math.max(0.005, Math.min(1, w)),
        h: Math.max(0.005, Math.min(1, h)),
      };
    } else if (objDrag.kind.startsWith("point-")) {
      const idx = parseInt(objDrag.kind.slice("point-".length), 10);
      const newPts = snap.points.map((p, i) =>
        i === idx ? [clamp01(p[0] + dx), clamp01(p[1] + dy)] : p
      );
      next = { ...snap, points: newPts };
    }
    if (next && onObjectChange) onObjectChange(next);
  };

  // ------ Rendering ------
  const classFor = (t) => {
    switch (t) {
      case "wall_external": return "overlay-wall-external overlay-hit";
      case "wall_internal": return "overlay-wall-internal overlay-hit";
      case "door": return "overlay-door overlay-hit";
      case "window": return "overlay-window overlay-hit";
      case "bathroom": return "overlay-bathroom overlay-hit";
      case "room": return "overlay-room overlay-hit";
      default: return "overlay-hit";
    }
  };

  const renderObj = (o, idx) => {
    const px = (v) => v * svgW;
    const py = (v) => v * svgH;
    const isSelected = o.id === selectedId;
    const handleClick = (e) => {
      e.stopPropagation();
      onSelect && onSelect(o);
    };
    const handleEnter = (e) =>
      !calibrateMode && setHover({ obj: o, x: e.clientX, y: e.clientY });
    const handleLeave = () => setHover(null);
    const strokeExtra = isSelected
      ? { strokeWidth: 4, filter: "drop-shadow(0 0 8px currentColor)" }
      : {};
    const bodyEvents = editMode
      ? {
          onMouseDown: (e) => beginObjDrag(e, o, "move"),
          onClick: handleClick,
          onMouseEnter: handleEnter,
          onMouseLeave: handleLeave,
          style: { ...strokeExtra, cursor: "move" },
        }
      : {
          onClick: handleClick,
          onMouseEnter: handleEnter,
          onMouseLeave: handleLeave,
          style: strokeExtra,
        };

    // wall polylines
    if (o.type === "wall_external" || o.type === "wall_internal") {
      if (o.points && o.points.length >= 2) {
        const d = o.points
          .map((p, i) => `${i === 0 ? "M" : "L"} ${px(p[0])} ${py(p[1])}`)
          .join(" ");
        return (
          <g key={o.id || idx}>
            <path
              d={d}
              className={classFor(o.type)}
              data-testid={`obj-${o.id}`}
              {...bodyEvents}
            />
            {editMode && isSelected &&
              o.points.map((p, i) => (
                <PointHandle
                  key={`pt-${i}`}
                  cx={px(p[0])}
                  cy={py(p[1])}
                  onMouseDown={(e) => beginObjDrag(e, o, `point-${i}`)}
                />
              ))}
          </g>
        );
      }
      return (
        <line
          key={o.id || idx}
          x1={px(o.x)} y1={py(o.y)}
          x2={px(o.x + (o.w || 0.05))} y2={py(o.y + (o.h || 0))}
          className={classFor(o.type)}
          {...bodyEvents}
        />
      );
    }
    // rect objects
    const rectX = px(o.x);
    const rectY = py(o.y);
    const rectW = Math.max(4, px(o.w));
    const rectH = Math.max(4, py(o.h));
    return (
      <g key={o.id || idx}>
        <rect
          x={rectX}
          y={rectY}
          width={rectW}
          height={rectH}
          rx={o.type === "door" || o.type === "window" ? 2 : 4}
          className={classFor(o.type)}
          data-testid={`obj-${o.id}`}
          {...bodyEvents}
        />
        {editMode && isSelected && (
          <>
            <CornerHandle cx={rectX} cy={rectY}
              onMouseDown={(e) => beginObjDrag(e, o, "corner-tl")} />
            <CornerHandle cx={rectX + rectW} cy={rectY}
              onMouseDown={(e) => beginObjDrag(e, o, "corner-tr")} />
            <CornerHandle cx={rectX} cy={rectY + rectH}
              onMouseDown={(e) => beginObjDrag(e, o, "corner-bl")} />
            <CornerHandle cx={rectX + rectW} cy={rectY + rectH}
              onMouseDown={(e) => beginObjDrag(e, o, "corner-br")} />
          </>
        )}
      </g>
    );
  };

  return (
    <div className="relative rounded-lg border border-border bg-card overflow-hidden">
      {/* Layers toolbar */}
      <div className="absolute top-3 left-3 z-20 glass rounded-lg border border-border p-1 flex items-center gap-0.5">
        <div className="px-2.5 py-1 text-[10px] uppercase tracking-widest text-muted-foreground font-mono-plex flex items-center gap-1.5">
          <Layers className="w-3 h-3" />
          Layers
        </div>
        {["walls", "doors", "windows", "rooms"].map((k) => (
          <button
            key={k}
            data-testid={ANALYSIS[`layer${k[0].toUpperCase() + k.slice(1)}`]}
            onClick={() => setLayers((l) => ({ ...l, [k]: !l[k] }))}
            className={`px-2.5 py-1 text-xs rounded capitalize transition-colors ${
              layers[k]
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60"
            }`}
          >
            {k}
          </button>
        ))}
      </div>

      {/* Zoom controls */}
      <div className="absolute top-3 right-3 z-20 glass rounded-lg border border-border p-1 flex items-center gap-1">
        <Button data-testid={ANALYSIS.zoomOut} variant="ghost" size="icon" className="w-7 h-7" onClick={zoomOut}>
          <Minus className="w-3.5 h-3.5" />
        </Button>
        <span className="text-xs font-mono-plex min-w-[36px] text-center">
          {(zoom * 100).toFixed(0)}%
        </span>
        <Button data-testid={ANALYSIS.zoomIn} variant="ghost" size="icon" className="w-7 h-7" onClick={zoomIn}>
          <Plus className="w-3.5 h-3.5" />
        </Button>
        <Button data-testid={ANALYSIS.zoomReset} variant="ghost" size="icon" className="w-7 h-7" onClick={reset}>
          <RotateCcw className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* Calibration hint */}
      {calibrateMode && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 glass border border-primary rounded-full px-4 py-1.5 text-xs font-mono-plex text-primary shadow-lg">
          {calibPts.length === 0
            ? "Click the start of a known-length segment"
            : "Click the end of the segment"}
        </div>
      )}

      {/* Canvas */}
      <div
        ref={wrapRef}
        data-testid={ANALYSIS.planViewer}
        className={`relative bp-grid-sm overflow-hidden select-none ${
          calibrateMode ? "cursor-crosshair" : "plan-canvas-cursor"
        }`}
        style={{ height: 600 }}
        onMouseDown={onCanvasMouseDown}
        onMouseMove={onCanvasMouseMove}
        onMouseUp={onCanvasMouseUp}
        onMouseLeave={onCanvasLeave}
      >
        <div
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
            transformOrigin: "center center",
            transition: panDrag || objDrag ? "none" : "transform 0.12s ease",
            width: svgW,
            height: svgH,
            position: "absolute",
            left: "50%",
            top: "50%",
            marginLeft: -svgW / 2,
            marginTop: -svgH / 2,
          }}
        >
          {image && (
            <img
              src={image}
              alt="floor plan"
              draggable={false}
              className="w-full h-full object-contain pointer-events-none"
              style={{ background: "white" }}
            />
          )}
          <svg
            ref={svgRef}
            width={svgW}
            height={svgH}
            viewBox={`0 0 ${svgW} ${svgH}`}
            className="absolute inset-0"
          >
            {visible.map(renderObj)}

            {/* Calibration overlay */}
            {calibrateMode && calibPts.length >= 1 && (
              <g>
                <circle
                  cx={calibPts[0][0] * svgW}
                  cy={calibPts[0][1] * svgH}
                  r={5}
                  fill="#ef4444"
                  stroke="white"
                  strokeWidth={1.5}
                />
                {calibPts.length === 1 && mousePt && (
                  <line
                    x1={calibPts[0][0] * svgW}
                    y1={calibPts[0][1] * svgH}
                    x2={mousePt[0] * svgW}
                    y2={mousePt[1] * svgH}
                    stroke="#ef4444"
                    strokeWidth={2}
                    strokeDasharray="6 4"
                  />
                )}
                {calibPts.length === 2 && (
                  <>
                    <line
                      x1={calibPts[0][0] * svgW}
                      y1={calibPts[0][1] * svgH}
                      x2={calibPts[1][0] * svgW}
                      y2={calibPts[1][1] * svgH}
                      stroke="#ef4444"
                      strokeWidth={2}
                    />
                    <circle
                      cx={calibPts[1][0] * svgW}
                      cy={calibPts[1][1] * svgH}
                      r={5}
                      fill="#ef4444"
                      stroke="white"
                      strokeWidth={1.5}
                    />
                  </>
                )}
              </g>
            )}
          </svg>
        </div>
      </div>

      {/* Hover tooltip */}
      {hover && (
        <div
          className="fixed z-50 pointer-events-none rounded-md border border-border bg-popover text-popover-foreground text-xs shadow-lg px-3 py-2 font-mono-plex"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="font-semibold text-foreground mb-0.5">
            {hover.obj.label || labelFor(hover.obj)}
          </div>
          <div className="text-muted-foreground">
            Type: {hover.obj.type.replace("_", " ")}
          </div>
          {hover.obj.width_ft != null && (
            <div className="text-muted-foreground">
              Width: {hover.obj.width_ft} ft
            </div>
          )}
          {hover.obj.length_ft != null && (
            <div className="text-muted-foreground">
              Length: {Number(hover.obj.length_ft).toFixed(1)} ft
            </div>
          )}
          <div className="text-muted-foreground">
            Confidence: {Math.round(hover.obj.confidence || 0)}%
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-3 left-3 z-20 glass rounded-lg border border-border px-3 py-2 flex flex-wrap items-center gap-4 text-[11px] font-mono-plex">
        <LegendItem color="var(--wall-color)" label="Walls" />
        <LegendItem color="var(--door-color)" label="Doors" />
        <LegendItem color="var(--window-color)" label="Windows" />
        <LegendItem color="var(--bathroom-color)" label="Bathrooms" />
        <LegendItem color="var(--room-color)" label="Rooms" />
      </div>
    </div>
  );
};

const CornerHandle = ({ cx, cy, onMouseDown }) => (
  <rect
    x={cx - 5}
    y={cy - 5}
    width={10}
    height={10}
    fill="white"
    stroke="hsl(var(--primary))"
    strokeWidth={1.5}
    style={{ cursor: "nwse-resize" }}
    onMouseDown={onMouseDown}
  />
);

const PointHandle = ({ cx, cy, onMouseDown }) => (
  <circle
    cx={cx}
    cy={cy}
    r={6}
    fill="white"
    stroke="hsl(var(--primary))"
    strokeWidth={1.5}
    style={{ cursor: "grab" }}
    onMouseDown={onMouseDown}
  />
);

const labelFor = (o) => {
  const map = {
    wall_external: "External Wall",
    wall_internal: "Internal Wall",
    door: "Door",
    window: "Window",
    bathroom: "Bathroom",
    room: "Room",
  };
  return map[o.type] || o.type;
};

const LegendItem = ({ color, label }) => (
  <span className="inline-flex items-center gap-1.5">
    <span
      className="w-2.5 h-2.5 rounded-sm"
      style={{ background: color, boxShadow: `0 0 6px ${color}` }}
    />
    {label}
  </span>
);

export default PlanViewer;
