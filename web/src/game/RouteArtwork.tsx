import type { Track } from "./types";

const palettes = {
  coast: { ground: "#64725e", road: "#343738", shoulder: "#a4a28c" },
  city: { ground: "#647175", road: "#34383b", shoulder: "#9b9f9c" },
  sunset: { ground: "#918067", road: "#3c3938", shoulder: "#b3a48b" },
  night: { ground: "#283237", road: "#272d32", shoulder: "#69757a" },
};

function Vehicle({ x, y, paint, truck = false }: { x: number; y: number; paint: string; truck?: boolean }) {
  const height = truck ? 52 : 33;
  return <g transform={`translate(${x} ${y})`}>
    <rect x="-7" y="-13" width="19" height={height} rx="3" fill="#10191d" opacity=".38" />
    <rect x="-9" y="-16" width="18" height={height} rx="3" fill={paint} stroke="#e9e4d0" strokeOpacity=".35" />
    <rect x="-7" y="-13" width="2" height={height - 6} fill="white" opacity=".22" />
    <path d="M-6-9H6L4-3H-4Z" fill="#263c43" />
    {truck ? <><rect x="-7" y="-1" width="14" height="34" rx="1" fill="#c9c5b8" /><path d="M-6 6H6M-6 12H6M-6 18H6M-6 24H6" stroke="#969e98" strokeWidth=".8" /></>
      : <><rect x="-4" y="-1" width="8" height="11" rx="1" fill={paint} /><path d="M-4 10H4L6 13H-6Z" fill="#283c42" /></>}
    <path d={`M-7 ${height - 18}H-3M3 ${height - 18}H7`} stroke="#e3765c" strokeWidth="2" />
    <path d="M-7-13H-3M3-13H7" stroke="#f7efd2" strokeWidth="2" />
  </g>;
}

export default function RouteArtwork({ track }: { track: Track }) {
  const palette = palettes[track.theme];
  const route = track.scenario;
  const lanes = route === "pressure" ? [
    { x: 136, y: 41, paint: "#a2acb0", truck: false }, { x: 178, y: 49, paint: "#a5ac9d", truck: true },
    { x: 220, y: 27, paint: "#c1ad86", truck: false }, { x: 136, y: 146, paint: "#8e9fa6", truck: false },
    { x: 220, y: 158, paint: "#aa9a98", truck: false },
  ] : route === "weave" ? [
    { x: 178, y: 23, paint: "#a6ac9f", truck: true }, { x: 136, y: 150, paint: "#7c9ba6", truck: false },
    { x: 220, y: 173, paint: "#c5a573", truck: false }, { x: 220, y: 57, paint: "#aaadb1", truck: false },
  ] : [
    { x: 178, y: 22, paint: "#a6ac9f", truck: true }, { x: 220, y: 143, paint: "#bd9f79", truck: false },
  ];
  return <svg viewBox="0 0 320 190" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <rect width="320" height="190" fill={palette.ground} />
    {track.theme === "coast" && <><path d="M0 0H75L44 190H0Z" fill="#527c84" /><path d="M58 0L25 190" stroke="#d7c9a1" strokeWidth="7" opacity=".5" /></>}
    <g transform="rotate(-16 178 95)">
      <rect x="102" y="-40" width="152" height="280" fill={palette.shoulder} />
      <rect x="114" y="-40" width="128" height="280" fill={palette.road} />
      <path d="M116-40V240M240-40V240" stroke="#ddd8bd" strokeWidth="2" />
      <path d="M157-40V240M199-40V240" stroke="#dfdfd1" strokeWidth="2" strokeDasharray="18 23" opacity=".65" />
      <path d="M106-40V240M250-40V240" stroke="#c2c5b8" strokeWidth="2" />
      {[0, 35, 70, 105, 140, 175].map((y) => <path key={y} d={`M103 ${y}H109M247 ${y}H253`} stroke="#e7e7d9" strokeWidth="3" />)}
      {lanes.map((vehicle, index) => <Vehicle key={index} {...vehicle} />)}
      <Vehicle x={178} y={131} paint="#efc45b" />
      {track.theme === "city" || track.theme === "night" ? <>
        <rect x="42" y="-20" width="44" height="76" fill="#1b292d" opacity=".25" /><rect x="35" y="-28" width="44" height="76" fill="#a0a9a4" />
        <rect x="42" y="-21" width="30" height="59" fill="#798a8b" /><rect x="52" y="-3" width="13" height="16" fill="#465e65" />
        <rect x="277" y="69" width="55" height="87" fill="#152329" opacity=".3" /><rect x="270" y="62" width="55" height="87" fill="#8b9999" />
        <path d="M276 78H317M276 92H317M276 106H317M276 120H317" stroke="#bbbbb0" strokeWidth="3" opacity=".6" />
      </> : [ [79, 26], [72, 125], [280, 64], [283, 165] ].map(([x, y], index) => <g key={index}>
        <ellipse cx={x + 4} cy={y + 6} rx="17" ry="14" fill="#19291d" opacity=".23" />
        <path d={`M${x - 17} ${y}l8-14 14-3 12 12-1 14-16 7-14-9Z`} fill="#455d43" />
        <ellipse cx={x - 4} cy={y - 5} rx="8" ry="7" fill="#9aa87a" opacity=".18" />
      </g>)}
    </g>
  </svg>;
}
