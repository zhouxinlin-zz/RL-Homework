export function Icon({
  name,
  size = 20,
}: {
  name:
    | "play"
    | "pause"
    | "back"
    | "settings"
    | "expand"
    | "close"
    | "flag"
    | "car"
    | "replay";
  size?: number;
}) {
  const paths = {
    play: "m8 5 11 7-11 7Z",
    pause: "M8 5v14M16 5v14",
    back: "m14 6-6 6 6 6M8 12h13",
    settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
    expand: "M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5",
    close: "m6 6 12 12M18 6 6 18",
    flag: "M5 21V3m0 1c5-5 9 5 14 0v10c-5 5-9-5-14 0",
    car: "m5 8 2-5h10l2 5M4 9h16v9H4ZM7 18v3M17 18v3M7 13h2M15 13h2",
    replay: "M4 10a8 8 0 1 1 1 8M4 3v7h7",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
