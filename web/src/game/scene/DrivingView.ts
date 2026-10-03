import * as THREE from "three";
import type { Vehicle, WorldFrame, Settings, Theme } from "../types";
import { CarLibrary, type CarModel } from "./assets";
import { Scenery, palettes } from "./scenery";

const trafficPaint = [
  "#aab8c0",
  "#456779",
  "#dcb857",
  "#b47661",
  "#729080",
  "#e4dfd1",
  "#7085a8",
];
type VisualCar = {
  root: THREE.Group;
  lamps: THREE.MeshStandardMaterial;
  indicators: THREE.Mesh[];
  wheels: THREE.Object3D[];
  paint: string;
};

export class DrivingView {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(48, 1, 0.2, 700);
  private scenery: Scenery;
  private cars = new Map<number, VisualCar>();
  private previous: WorldFrame | null = null;
  private current: WorldFrame | null = null;
  private received = 0;
  private frameMs = 200;
  private lastTime = 0;
  private library: CarLibrary;
  private theme: Theme;
  private guide: THREE.Mesh;
  private beacon: THREE.Mesh;
  private sharedGeometry = new THREE.BoxGeometry(1, 1, 1);
  private blinkMaterial = new THREE.MeshStandardMaterial({
    color: 0xffba49,
    emissive: 0xff8b18,
    emissiveIntensity: 2,
  });
  private look = new THREE.Vector3();
  private cameraX = 0;
  private crashStart = -1;
  private particles: THREE.InstancedMesh;
  private matrix = new THREE.Matrix4();
  private disposed = false;

  constructor(library: CarLibrary, theme: Theme) {
    this.library = library;
    this.theme = theme;
    this.scenery = new Scenery(theme);
    this.scene.add(this.scenery.root);
    const p = palettes[theme];
    this.scene.background = new THREE.Color(p.fog);
    this.scene.fog = new THREE.Fog(p.fog, 95, 310);
    this.scene.add(
      new THREE.HemisphereLight(
        0xe3f1ff,
        p.ground,
        theme === "night" ? 1.4 : 2.3,
      ),
    );
    const sun = new THREE.DirectionalLight(
      p.sun,
      theme === "night" ? 1.7 : 3.1,
    );
    sun.position.set(-30, 45, 10);
    sun.target.position.set(0, 0, -30);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, {
      left: -42,
      right: 42,
      top: 85,
      bottom: -35,
      near: 0.5,
      far: 180,
    });
    sun.shadow.normalBias = 0.08;
    sun.shadow.bias = -0.00015;
    this.scene.add(sun, sun.target);
    const rim = new THREE.DirectionalLight(0xdaedff, 0.5);
    rim.position.set(15, 12, -40);
    this.scene.add(rim);
    this.guide = new THREE.Mesh(
      new THREE.PlaneGeometry(0.1, 7),
      new THREE.MeshBasicMaterial({
        color: 0xbfe7d5,
        transparent: true,
        opacity: 0.48,
        depthWrite: false,
      }),
    );
    this.guide.rotation.x = -Math.PI / 2;
    this.scene.add(this.guide);
    this.beacon = new THREE.Mesh(
      new THREE.RingGeometry(0.42, 0.55, 3, 1, Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: 0xccebe0,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.85,
        depthWrite: false,
      }),
    );
    this.beacon.rotation.x = -Math.PI / 2;
    this.scene.add(this.beacon);
    this.particles = new THREE.InstancedMesh(
      new THREE.BoxGeometry(0.08, 0.08, 0.3),
      new THREE.MeshBasicMaterial({ color: 0xffce77 }),
      16,
    );
    this.particles.frustumCulled = false;
    this.particles.visible = false;
    this.scene.add(this.particles);
  }

  setFrame(
    frame: WorldFrame,
    now: number,
    rate: number,
    replay: boolean,
    reset: boolean,
  ) {
    if (frame === this.current) return;
    if (!reset && frame.time_s === this.current?.time_s) {
      this.current = frame;
      return;
    }
    const delta = frame.time_s - (this.current?.time_s ?? frame.time_s);
    const discontinuity = reset || delta <= 0 || delta > 0.5;
    this.previous = discontinuity ? frame : this.current;
    this.current = frame;
    this.frameMs = replay ? Math.max(30, (delta * 1000) / rate) : 200;
    this.received = now;
    if (discontinuity) {
      this.crashStart = -1;
      this.cameraX =
        ((frame.vehicles.find((v) => v.id === frame.ego_id)?.y ?? 4) - 4) * 0.2;
    }
  }

  private createCar(
    vehicle: Vehicle,
    ego: boolean,
    settings: Settings,
    rival: boolean,
  ): VisualCar {
    const kind = ego ? settings.vehicle : vehicle.kind;
    const name: CarModel =
      vehicle.length > 6.5 || kind === "truck"
        ? "truck"
        : kind === "van"
          ? "delivery"
          : kind === "suv"
            ? "suv"
            : ego
              ? kind === "touring"
                ? "sedan"
                : "sedan-sports"
              : (["sedan", "hatchback-sports", "van", "sedan-sports"] as const)[
                  vehicle.id % 4
                ];
    const paint = ego
      ? rival
        ? "#c67750"
        : settings.color
      : trafficPaint[vehicle.id % trafficPaint.length];
    const root = new THREE.Group();
    const model = this.library.car(name, paint);
    model.scale.multiply(
      new THREE.Vector3(vehicle.width, vehicle.width, vehicle.length),
    );
    root.add(model);
    const wheels: THREE.Object3D[] = [];
    model.traverse((object) => {
      if (object.name.startsWith("wheel-")) wheels.push(object);
    });
    const lamps = new THREE.MeshStandardMaterial({
      color: 0x9c2627,
      emissive: 0xff2916,
      emissiveIntensity: 0.25,
    });
    const indicators: THREE.Mesh[] = [];
    for (const side of [-1, 1]) {
      const lamp = new THREE.Mesh(this.sharedGeometry, lamps);
      lamp.scale.set(vehicle.width * 0.21, 0.12, 0.055);
      lamp.position.set(
        side * vehicle.width * 0.32,
        vehicle.width * 0.37,
        vehicle.length / 2 + 0.025,
      );
      root.add(lamp);
      const indicator = new THREE.Mesh(this.sharedGeometry, this.blinkMaterial);
      indicator.scale.set(0.14, 0.1, 0.06);
      indicator.position.set(
        side * vehicle.width * 0.46,
        vehicle.width * 0.37,
        vehicle.length / 2 + 0.03,
      );
      indicator.visible = false;
      root.add(indicator);
      indicators.push(indicator);
    }
    if (this.theme === "night") {
      const beam = new THREE.Mesh(
        new THREE.PlaneGeometry(vehicle.width * 1.6, 10),
        new THREE.MeshBasicMaterial({
          color: 0xffefb9,
          transparent: true,
          opacity: 0.055,
          depthWrite: false,
        }),
      );
      beam.rotation.x = -Math.PI / 2;
      beam.position.set(0, 0.035, -vehicle.length / 2 - 5);
      root.add(beam);
    }
    this.scene.add(root);
    return { root, lamps, indicators, wheels, paint };
  }

  render(
    now: number,
    settings: Settings,
    rival: boolean,
    menu: boolean,
    moving: boolean,
    aspect: number,
  ) {
    const frame = this.current;
    if (!frame) return;
    const dt = Math.min(0.05, Math.max(0, (now - this.lastTime) / 1000));
    this.lastTime = now;
    const ego = frame.vehicles.find((vehicle) => vehicle.id === frame.ego_id);
    if (!ego) return;
    const previousCars = new Map(
      this.previous?.vehicles.map((v) => [v.id, v]) ?? [],
    );
    // Display interpolation stays within authoritative snapshots; physics stays on the server.
    const alpha = moving
      ? Math.min(1, Math.max(0, (now - this.received) / this.frameMs))
      : 1;
    const oldEgo = previousCars.get(ego.id) ?? ego;
    const egoX = THREE.MathUtils.lerp(oldEgo.x, ego.x, alpha);
    const egoY = THREE.MathUtils.lerp(oldEgo.y, ego.y, alpha) - 4;
    this.scenery.update(egoX);
    this.camera.aspect = aspect;
    if (menu) {
      this.camera.fov = 43;
      this.camera.position.set(20, 16, 26);
      this.camera.lookAt(-5, 0, -19);
    } else {
      this.cameraX += (egoY * 0.2 - this.cameraX) * (1 - Math.exp(-dt * 5));
      this.camera.fov = 48;
      this.camera.position.set(
        settings.reducedMotion ? 0 : this.cameraX,
        28,
        32,
      );
      this.look.set(settings.reducedMotion ? 0 : this.cameraX * 0.4, 0, -13);
      this.camera.lookAt(this.look);
    }
    this.camera.updateProjectionMatrix();
    const used = new Set<number>();
    for (const vehicle of frame.vehicles) {
      if (vehicle.x - ego.x > 270 || vehicle.x - ego.x < -45) continue;
      used.add(vehicle.id);
      const isEgo = vehicle.id === frame.ego_id;
      let car = this.cars.get(vehicle.id);
      if (car && isEgo && car.paint !== (rival ? "#c67750" : settings.color)) {
        this.removeCar(vehicle.id, car);
        car = undefined;
      }
      if (!car) {
        car = this.createCar(vehicle, isEgo, settings, rival);
        this.cars.set(vehicle.id, car);
      }
      const previous = previousCars.get(vehicle.id) ?? vehicle;
      car.root.position.set(
        THREE.MathUtils.lerp(previous.y, vehicle.y, alpha) - 4,
        0.015,
        -(THREE.MathUtils.lerp(previous.x, vehicle.x, alpha) - egoX),
      );
      car.root.rotation.y = -THREE.MathUtils.lerp(
        previous.heading,
        vehicle.heading,
        alpha,
      );
      const braking =
        vehicle.speed < previous.speed - 0.06 || (isEgo && frame.action === 4);
      car.lamps.emissiveIntensity = braking || vehicle.crashed ? 3 : 0.35;
      const turning =
        isEgo && frame.target_lane !== undefined
          ? frame.target_lane * 4 - vehicle.y
          : vehicle.heading * 8;
      car.indicators.forEach((indicator, index) => {
        indicator.visible =
          Math.abs(turning) > 0.3 &&
          Math.floor(frame.time_s * 3) % 2 === 0 &&
          (index === 0 ? turning < 0 : turning > 0);
      });
      if (moving && !vehicle.crashed)
        for (const wheel of car.wheels)
          wheel.rotation.x -= (vehicle.speed * dt) / 0.35;
    }
    for (const [id, car] of this.cars)
      if (!used.has(id)) this.removeCar(id, car);
    this.guide.visible = settings.guides && !menu && !ego.crashed;
    this.guide.position.set(
      (frame.target_lane ?? Math.round(ego.y / 4)) * 4 - 4,
      0.025,
      -8,
    );
    this.beacon.visible = !menu && !ego.crashed;
    this.beacon.position.set(egoY, 0.04, ego.length / 2 + 1.1);
    (this.beacon.material as THREE.MeshBasicMaterial).color.set(
      rival ? 0xeac2a2 : 0xb9ebdc,
    );
    if (ego.crashed && !oldEgo.crashed && this.crashStart < 0)
      this.crashStart = now;
    const impact = this.crashStart < 0 ? 2 : (now - this.crashStart) / 1000;
    this.particles.visible = impact < 0.65 && !settings.reducedMotion;
    if (this.particles.visible) {
      for (let i = 0; i < 16; i++) {
        const angle = i * 2.3999;
        this.matrix.makeTranslation(
          egoY + Math.sin(angle) * impact * 6,
          0.2 + Math.max(0, impact * 3 - impact * impact * 6),
          -ego.length / 2 + Math.cos(angle) * impact * 6,
        );
        this.particles.setMatrixAt(i, this.matrix);
      }
      this.particles.instanceMatrix.needsUpdate = true;
    }
  }

  private removeCar(id: number, car: VisualCar) {
    this.scene.remove(car.root);
    car.lamps.dispose();
    car.root.traverse((object) => {
      if (
        object instanceof THREE.Mesh &&
        object.geometry.type === "PlaneGeometry"
      ) {
        object.geometry.dispose();
        (object.material as THREE.Material).dispose();
      }
    });
    this.cars.delete(id);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.scenery.dispose();
    for (const [id, car] of this.cars) this.removeCar(id, car);
    for (const mesh of [this.guide, this.beacon, this.particles]) {
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
    }
    this.particles.dispose();
    this.sharedGeometry.dispose();
    this.blinkMaterial.dispose();
    this.scene.traverse((object) => {
      if (object instanceof THREE.DirectionalLight) object.dispose();
    });
    this.scene.clear();
  }
}
