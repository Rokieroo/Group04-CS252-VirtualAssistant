/** Equal-area radial lanes inside y² <= H²*x/L, clipped at x=L. */
export function rootGeometry(count: number) {
  const L = 680,
    H = 175,
    steps = 6000;
  const maxRadius = (angle: number) =>
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
        ((maxRadius(samples[i - 1]) ** 2 + maxRadius(samples[i]) ** 2) / 4) *
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
    return samples[low];
  }
  const boundaries = Array.from({ length: count + 1 }, (_, i) =>
    quantile(count ? i / count : 0),
  );
  return {
    boundaries,
    maxRadius,
    lane: (index: number) => ({
      low: boundaries[index],
      high: boundaries[index + 1],
      center: quantile((index + 0.5) / count),
    }),
    point: (angle: number, radius: number) => ({
      x: 84 + Math.cos(angle) * radius,
      y: 260 + Math.sin(angle) * radius,
    }),
  };
}
export function coursePoints(index: number, count: number, nodes: number) {
  const geo = rootGeometry(count),
    lane = geo.lane(index);
  return Array.from({ length: nodes }, (_, j) => {
    const progress = (j + 1) / Math.max(nodes, 1);
    const variation = Math.sin((j + 1) * 2.1 + index) * 0.12;
    const angle =
      lane.center +
      variation *
        Math.min(0.12, lane.center - lane.low, lane.high - lane.center);
    return geo.point(angle, geo.maxRadius(angle) * (0.15 + 0.81 * progress));
  });
}
