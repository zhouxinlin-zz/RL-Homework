import type { WorldFrame } from "../live/types";

import { nearbyTraffic } from "./trafficProjection";

export default function TrafficPreview({
  frame,
  player = false,
}: {
  frame: WorldFrame;
  player?: boolean;
}) {
  const vehicles = nearbyTraffic(frame);
  if (!vehicles.length) return null;
  const label = player ? "你的周车" : "周车预览";
  return (
    <aside className="traffic-preview" aria-label={label}>
      <header>
        <span>{label}</span>
        <i className="preview-direction" aria-hidden="true">
          ↑
        </i>
      </header>
      <div className="traffic-map">
        <svg
          viewBox="0 0 100 180"
          role="img"
          aria-label="本车前方120米、后方80米内的车辆位置"
          preserveAspectRatio="none"
        >
          <rect
            x="0"
            y="0"
            width="100"
            height="180"
            rx="5"
            className="preview-road"
          />
          <path d="M33.33 0V180 M66.67 0V180" className="preview-lanes" />
          <path d="M0 108H100" className="preview-origin" />
          <path d="M0 54H100 M0 162H100" className="preview-distance" />
          {vehicles.map((vehicle) => (
            <g
              key={vehicle.id}
              data-vehicle-id={vehicle.id}
              className={`preview-vehicle ${vehicle.ego ? "is-ego" : ""} ${vehicle.crashed ? "is-crashed" : ""}`}
              style={{ transform: `translate(${vehicle.x}px, ${vehicle.y}px)` }}
            >
              <title>
                {vehicle.ego
                  ? "本车"
                  : `${vehicle.distance >= 0 ? "前方" : "后方"}${Math.round(Math.abs(vehicle.distance))}米，${Math.round(vehicle.speed)}公里每小时`}
              </title>
              {vehicle.ego && (
                <rect
                  x="-8"
                  y="-9"
                  width="16"
                  height="18"
                  rx="4"
                  className="preview-ego-halo"
                />
              )}
              <rect
                x={-vehicle.width / 2}
                y={-vehicle.length / 2}
                width={vehicle.width}
                height={vehicle.length}
                rx="1.5"
              />
              {vehicle.ego ? (
                <path d="M-2 -6L0 -9L2 -6" className="preview-speed-arrow" />
              ) : (
                Math.abs(vehicle.relativeSpeed) > 1 && (
                  <path
                    d={
                      vehicle.relativeSpeed > 0
                        ? "M-2 -7L0 -10L2 -7"
                        : "M-2 7L0 10L2 7"
                    }
                    className="preview-speed-arrow"
                  />
                )
              )}
            </g>
          ))}
        </svg>
      </div>
      <footer>
        <span>前 120 m</span>
        <span>后 80 m</span>
      </footer>
    </aside>
  );
}
