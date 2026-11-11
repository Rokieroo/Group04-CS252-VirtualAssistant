/** Equal-area radial lanes inside y² <= H²*x/L, clipped at x=L. */
export function rootGeometry(count: number, scale = 1) {
  const L = 680,
    H = 175,
    steps = 6000;
  const baseMaxRadius = (angle: number) =>
    Math.min(
      L / Math.cos(angle),
      (H * H * Math.cos(angle)) / (L * Math.sin(angle) ** 2),
    );
  const samples = Array.from(
    { length: steps + 1 },
    (_, i) => -Math.PI / 2 + 0.00001 + ((Math.PI - 0.00002) * i) / steps,
  );
  const area = [0];
  for (let i = 1; i <= steps; i++)
    area.push(
      area[i - 1] +
        ((baseMaxRadius(samples[i - 1]) ** 2 + baseMaxRadius(samples[i]) ** 2) /
          4) *
          (samples[i] - samples[i - 1]),
    );
  function quantile(q: number) {
    const target = q * area[steps];
    let low = 0,
      high = steps;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (area[mid] < target) low = mid + 1;
      else high = mid;
    }
    if (low === 0) return samples[0];
    const fraction = (target - area[low - 1]) / (area[low] - area[low - 1]);
    return samples[low - 1] + fraction * (samples[low] - samples[low - 1]);
  }
  const boundaries = Array.from({ length: count + 1 }, (_, i) =>
    quantile(count ? i / count : 0),
  );
  return {
    boundaries,
    scale,
    origin: { x: 84, y: 85 + H * scale },
    width: 180 + L * scale,
    height: 170 + 2 * H * scale,
    parabola: `M${84 + L * scale} 85 Q${84 - L * scale} ${85 + H * scale} ${84 + L * scale} ${85 + 2 * H * scale}`,
    maxRadius: (angle: number) => baseMaxRadius(angle) * scale,
    lane: (index: number) => ({
      low: boundaries[index],
      high: boundaries[index + 1],
      center: quantile((index + 0.5) / count),
    }),
    point: (angle: number, radius: number) => ({
      x: 84 + Math.cos(angle) * radius,
      y: 85 + H * scale + Math.sin(angle) * radius,
    }),
  };
}

// Includes the 12px halo, its focus outline, and clearance from sector borders.
export const NODE_EXTENT = 15;
const BAND_GAP = 4,
  MIN_SLOT = 2 * NODE_EXTENT + 16 + BAND_GAP;
export type PolarPosition = { angle: number; radius: number };
export function rootLayout(nodeCounts: number[]) {
  const base = rootGeometry(nodeCounts.length);
  const corridors = nodeCounts.map((nodes, i) => {
    const lane = base.lane(i);
    const half = Math.min(
      0.12,
      (lane.center - lane.low) * 0.45,
      (lane.high - lane.center) * 0.45,
    );
    const lowAngle = lane.center - half,
      highAngle = lane.center + half;
    const pad = Math.min(
      0.25,
      (lowAngle - lane.low) / 2,
      (lane.high - highAngle) / 2,
    );
    const start = Math.max(60, NODE_EXTENT / Math.sin(pad));
    // A common safe radius across the whole corridor AND the node's angular footprint.
    const cap = Math.min(
      680,
      base.maxRadius(lowAngle - pad),
      base.maxRadius(highAngle + pad),
    );
    return { nodes, lowAngle, highAngle, start, cap };
  });
  const scale = Math.max(
    1,
    ...corridors
      .filter((c) => c.nodes > 0)
      .map((c) => (c.start + c.nodes * MIN_SLOT + NODE_EXTENT) / c.cap),
  );
  const geo = rootGeometry(nodeCounts.length, scale);
  const courses = corridors.map((c) => {
    const end = c.cap * scale - NODE_EXTENT;
    const slot = c.nodes ? (end - c.start) / c.nodes : 0;
    return {
      ...c,
      bands: Array.from({ length: c.nodes }, (_, n) => ({
        low: c.start + n * slot + BAND_GAP / 2,
        high: c.start + (n + 1) * slot - BAND_GAP / 2,
      })),
    };
  });
  const project = (course: number, node: number, requested?: PolarPosition) => {
    const c = courses[course],
      band = c.bands[node];
    const angle = Math.max(
      c.lowAngle,
      Math.min(
        c.highAngle,
        requested?.angle ??
          (c.lowAngle + c.highAngle) / 2 +
            Math.sin((node + 1) * 2.1 + course) *
              (c.highAngle - c.lowAngle) *
              0.3,
      ),
    );
    const radius = Math.max(
      band.low + NODE_EXTENT + 0.001,
      Math.min(
        band.high - NODE_EXTENT - 0.001,
        requested?.radius ?? (band.low + band.high) / 2,
      ),
    );
    return { ...geo.point(angle, radius), angle, radius };
  };
  return { geo, courses, project };
}
export function coursePoints(index: number, count: number, nodes: number) {
  // Kept for existing consumers; the rendered multi-course graph uses one shared layout.
  const counts = Array.from({ length: count }, (_, i) =>
    i === index ? nodes : 0,
  );
  const layout = rootLayout(counts);
  return Array.from({ length: nodes }, (_, j) => layout.project(index, j));
}
