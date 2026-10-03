import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const names = [
  "sedan-sports",
  "sedan",
  "hatchback-sports",
  "suv",
  "van",
  "delivery",
  "truck",
] as const;
export type CarModel = (typeof names)[number];

/** One shared asset library for both views; all files are served locally. */
export class CarLibrary {
  private templates = new Map<CarModel, THREE.Group>();
  private variants = new Map<string, THREE.Group>();

  async load() {
    const loader = new GLTFLoader();
    // Wait for all loads, including on failure, so teardown cannot race a late asset.
    const results = await Promise.allSettled(
      names.map(async (name) => {
        const gltf = await loader.loadAsync(`/models/cars/${name}.glb`);
        this.templates.set(name, gltf.scene);
      }),
    );
    const failed = results.find((result) => result.status === "rejected");
    if (failed?.status === "rejected") throw failed.reason;
  }

  car(name: CarModel, paint: string): THREE.Group {
    const key = `${name}:${paint}`;
    let variant = this.variants.get(key);
    if (!variant) {
      variant = this.templates.get(name)!.clone(true);
      const target = new THREE.Color(paint);
      variant.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        const source = object.material as THREE.MeshStandardMaterial;
        const texture = source.map;
        const uv = object.geometry.getAttribute("uv");
        if (!texture || !uv) return;
        const canvas = document.createElement("canvas");
        const image = texture.image as HTMLImageElement | ImageBitmap;
        canvas.width = image.width;
        canvas.height = image.height;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(image, 0, 0);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        const samples: THREE.Color[] = [];
        const buckets = new Map<number, number>();
        const bucketIds: number[] = [];
        const hsl = { h: 0, s: 0, l: 0 };
        for (let i = 0; i < uv.count; i++) {
          const u = THREE.MathUtils.clamp(uv.getX(i), 0, 0.9999);
          const v = THREE.MathUtils.clamp(uv.getY(i), 0, 0.9999);
          const x = Math.floor(u * canvas.width);
          const y = Math.floor(
            (texture.flipY ? 1 - v : v) * (canvas.height - 1),
          );
          const offset = (y * canvas.width + x) * 4;
          const color = new THREE.Color().setRGB(
            pixels[offset] / 255,
            pixels[offset + 1] / 255,
            pixels[offset + 2] / 255,
            THREE.SRGBColorSpace,
          );
          samples.push(color);
          const bucket = Math.floor(x / 64) + 8 * Math.floor(y / 128);
          bucketIds.push(bucket);
          color.getHSL(hsl);
          if (hsl.s > 0.35 && hsl.l > 0.08 && hsl.l < 0.65)
            buckets.set(bucket, (buckets.get(bucket) ?? 0) + 1);
        }
        const dominant = [...buckets].sort((a, b) => b[1] - a[1])[0]?.[0];
        const repaint = object.name === "body" || object.name === "spoiler";
        const colors = new Float32Array(uv.count * 3);
        samples.forEach((color, i) => {
          // The pale blue palette swatch is window glass; give it a dark tint.
          if (object.name === "body" && bucketIds[i] === 24)
            color.set(0x365c70);
          (repaint && bucketIds[i] === dominant ? target : color).toArray(
            colors,
            i * 3,
          );
        });
        object.geometry = object.geometry.clone();
        object.geometry.setAttribute(
          "color",
          new THREE.BufferAttribute(colors, 3),
        );
        object.material = new THREE.MeshStandardMaterial({
          vertexColors: true,
          roughness: 0.48,
          metalness: 0.12,
        });
        object.castShadow = true;
        object.receiveShadow = true;
      });
      // Kenney models face +Z. The driving world advances toward -Z.
      variant.rotation.y = Math.PI;
      variant.updateMatrixWorld(true);
      const bounds = new THREE.Box3().setFromObject(variant);
      const center = bounds.getCenter(new THREE.Vector3());
      variant.position.set(-center.x, -bounds.min.y, -center.z);
      const normalized = new THREE.Group();
      normalized.add(variant);
      const size = bounds.getSize(new THREE.Vector3());
      normalized.scale.set(1 / size.x, 1 / size.x, 1 / size.z);
      this.variants.set(key, normalized);
      variant = normalized;
    }
    return variant.clone(true);
  }

  dispose() {
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    const bitmaps = new Set<ImageBitmap>();
    for (const root of [...this.templates.values(), ...this.variants.values()])
      root.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        geometries.add(object.geometry);
        for (const material of Array.isArray(object.material)
          ? object.material
          : [object.material]) {
          materials.add(material);
          if (material.map) {
            textures.add(material.map);
            if (
              typeof ImageBitmap !== "undefined" &&
              material.map.image instanceof ImageBitmap
            )
              bitmaps.add(material.map.image);
          }
        }
      });
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
    // Texture.dispose releases GPU resources; GLTFLoader bitmaps also own CPU memory.
    bitmaps.forEach((bitmap) => bitmap.close());
    this.templates.clear();
    this.variants.clear();
  }
}
