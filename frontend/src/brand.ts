// Product name and tagline. Single source of truth: config/brand.json (shared with the backend).
import brand from "../../config/brand.json";

export const BRAND: { name: string; tagline: string; slug: string } = brand;
