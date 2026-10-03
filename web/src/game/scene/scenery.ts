import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { Theme } from "../types";

export const palettes = {
  coast: {
    sky: 0xb7d9df,
    ground: 0x859667,
    verge: 0xc5b58a,
    road: 0x3c454b,
    tree: 0x486e52,
    sun: 0xfff2d4,
    fog: 0xc8d9cb,
  },
  city: {
    sky: 0xb4c5d0,
    ground: 0x86908a,
    verge: 0xa6aaa4,
    road: 0x3e454c,
    tree: 0x426e59,
    sun: 0xffedd7,
    fog: 0xbfcdd2,
  },
  sunset: {
    sky: 0xe3b8a1,
    ground: 0x9e9e74,
    verge: 0xcab08c,
    road: 0x424650,
    tree: 0x607251,
    sun: 0xffc482,
    fog: 0xe3c3ae,
  },
  night: {
    sky: 0x263744,
    ground: 0x314247,
    verge: 0x667274,
    road: 0x303b47,
    tree: 0x304c47,
    sun: 0xa1c8f1,
    fog: 0x415865,
  },
};

function roadTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext("2d")!;
  const pixels = ctx.createImageData(256, 256);
  let seed = 7193;
  for (let i = 0; i < pixels.data.length; i += 4) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const value = 182 + (seed >>> 27);
    pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value;
    pixels.data[i + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(3, 100);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

/** Roadside geometry is built once and merged by material, then recycled in tiles. */
export class Scenery {
  readonly root = new THREE.Group();
  private tiles: THREE.Group[] = [];
  private materialCache = new Map<number, THREE.MeshStandardMaterial>();
  private texture = roadTexture();
  private dashes: THREE.InstancedMesh;
  private matrix = new THREE.Matrix4();
  private disposed = false;

  constructor(theme: Theme) {
    const p = palettes[theme];
    const material = (color: number) => {
      if (!this.materialCache.has(color))
        this.materialCache.set(
          color,
          new THREE.MeshStandardMaterial({ color, roughness: 0.9 }),
        );
      return this.materialCache.get(color)!;
    };
    const plane = (
      width: number,
      length: number,
      x: number,
      height: number,
      mat: THREE.Material,
    ) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, length), mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set(x, height, -150);
      mesh.receiveShadow = true;
      this.root.add(mesh);
    };
    plane(1000, 1000, 0, -0.12, material(p.ground));
    plane(17, 600, 0, -0.035, material(p.verge));
    const asphalt = new THREE.MeshStandardMaterial({
      color: p.road,
      map: this.texture,
      roughness: 0.94,
    });
    plane(14.5, 600, 0, 0, asphalt);
    for (const side of [-1, 1]) {
      plane(0.13, 600, side * 6.1, 0.018, material(0xf4eddc));
      plane(0.09, 600, side * 6.4, 0.018, material(0xa4a69f));
    }
    if (theme === "coast") {
      plane(350, 1000, -194, -0.08, material(0x639ea9));
      plane(5, 1000, -18, -0.04, material(0xe0ceaa));
    }
    this.dashes = new THREE.InstancedMesh(
      new THREE.PlaneGeometry(0.15, 4.5),
      material(0xf0ecdf),
      100,
    );
    this.dashes.rotation.x = -Math.PI / 2;
    this.dashes.position.y = 0.02;
    this.dashes.frustumCulled = false;
    this.root.add(this.dashes);
    for (let tileIndex = 0; tileIndex < 7; tileIndex++) {
      const tile = new THREE.Group();
      const buckets = new Map<number, THREE.BufferGeometry[]>();
      let randomState = 191 + tileIndex * 197;
      const random = () => {
        randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0;
        return randomState / 4294967296;
      };
      const add = (
        geometry: THREE.BufferGeometry,
        color: number,
        x: number,
        y: number,
        z: number,
        rotation = 0,
      ) => {
        geometry.rotateY(rotation);
        geometry.translate(x, y, z);
        if (!buckets.has(color)) buckets.set(color, []);
        buckets.get(color)!.push(geometry);
      };
      const box = (
        w: number,
        h: number,
        d: number,
        color: number,
        x: number,
        y: number,
        z: number,
      ) => add(new THREE.BoxGeometry(w, h, d), color, x, y, z);
      for (const side of [-1, 1]) {
        // Thin guardrails preserve visibility of adjacent traffic.
        box(0.12, 0.32, 60, 0x909d9b, side * 7.8, 0.78, 0);
        for (let z = -27; z < 30; z += 6) {
          box(0.12, 0.8, 0.12, 0x758582, side * 7.8, 0.4, z);
          box(0.1, 0.12, 0.24, 0xf3cf78, side * 7.71, 0.82, z);
        }
        for (let i = 0; i < 8; i++) {
          if (theme === "coast" && side === -1 && i > 2) continue;
          const x = side * (10 + random() * (theme === "coast" ? 7 : 23));
          const z = -30 + random() * 60;
          const height = 2.8 + random() * 3.8;
          box(0.24, height * 0.6, 0.24, 0x6b6950, x, height * 0.3, z);
          const tree = new THREE.IcosahedronGeometry(height * 0.36, 0);
          tree.scale(1, 1.35, 1);
          add(
            tree,
            i % 3 ? p.tree : 0x799163,
            x,
            height * 0.85,
            z,
            random() * 6,
          );
        }
        if (theme === "city" || theme === "night") {
          for (let i = 0; i < 4; i++) {
            const height = 6 + random() * 18;
            const x = side * (23 + random() * 18),
              z = i * 16 - 25;
            box(7, height, 10, i % 2 ? 0x929c9d : 0xb8b6a8, x, height / 2, z);
            box(7.3, 0.25, 10.3, 0x667c83, x, height, z);
            for (let y = 2; y < height - 1; y += 2.6) {
              box(
                0.025,
                0.95,
                7.5,
                theme === "night" ? 0xe4be7a : 0x58747e,
                x - side * 3.51,
                y,
                z,
              );
              box(
                5.6,
                0.95,
                0.025,
                theme === "night" ? 0xe4be7a : 0x58747e,
                x,
                y,
                z + 5.01,
              );
            }
          }
        } else if (side === 1) {
          for (let i = 0; i < 2; i++) {
            const hill = new THREE.IcosahedronGeometry(18 + random() * 20, 1);
            hill.scale(1.2, 0.42, 0.85);
            add(hill, i ? 0x839775 : 0x748c70, 55 + i * 37, 0, i * 35 - 15);
          }
        }
        // Lamps are offset from the carriageway so they never hide a vehicle.
        box(0.16, 7.5, 0.16, 0x758581, side * 9, 3.75, 14);
        box(1.5, 0.16, 0.15, 0x758581, side * 8.3, 7.5, 14);
        box(0.6, 0.08, 0.3, 0xf6e3b0, side * 7.8, 7.4, 14);
      }
      if (theme === "coast") {
        for (let i = 0; i < 12; i++) {
          box(
            2 + random() * 6,
            0.008,
            0.06,
            0x92b8bc,
            -23 - random() * 75,
            -0.06,
            random() * 60 - 30,
          );
        }
      }
      // Shoulder signs are kept away from driving lanes.
      box(0.12, 2.2, 0.12, 0x7c8984, 8.7, 1.1, -15);
      box(1.1, 0.9, 0.09, 0x367b70, 8.7, 2.2, -15);
      box(0.58, 0.08, 0.1, 0xe6edd8, 8.7, 2.4, -14.95);
      box(0.32, 0.08, 0.1, 0xe6edd8, 8.7, 2.12, -14.95);
      for (const [color, geometries] of buckets) {
        const mesh = new THREE.Mesh(
          mergeGeometries(geometries),
          material(color),
        );
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        tile.add(mesh);
        geometries.forEach((geometry) => geometry.dispose());
      }
      this.tiles.push(tile);
      this.root.add(tile);
    }
  }

  update(distance: number) {
    this.texture.offset.y = -(distance % 6) / 6;
    this.tiles.forEach((tile, index) => {
      tile.position.z = ((((distance + index * 60) % 420) + 420) % 420) - 340;
    });
    for (let i = 0; i < 100; i++) {
      this.matrix.makeTranslation(
        i % 2 ? -2 : 2,
        Math.floor(i / 2) * 12 - (((distance % 12) + 12) % 12) - 55,
        0,
      );
      this.dashes.setMatrixAt(i, this.matrix);
    }
    this.dashes.instanceMatrix.needsUpdate = true;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.root.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.geometry.dispose();
        if (object instanceof THREE.InstancedMesh) object.dispose();
        if (!Array.isArray(object.material)) object.material.dispose();
      }
    });
    this.texture.dispose();
  }
}
