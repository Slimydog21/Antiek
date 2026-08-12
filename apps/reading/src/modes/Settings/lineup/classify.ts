import {
  ROLE_INVENTORY,
  type Classification,
  type GeneralSlot,
  type RoleRecord,
} from "./inventory";

export function classifyRole(role: string): Classification {
  const record = ROLE_INVENTORY.find((item) => item.role === role);
  if (!record) {
    throw new Error(`Role ${JSON.stringify(role)} is not in the shipped inventory`);
  }
  return record.classification;
}

export function inventoryRecord(role: string): RoleRecord {
  const record = ROLE_INVENTORY.find((item) => item.role === role);
  if (!record) {
    throw new Error(`Role ${JSON.stringify(role)} is not in the shipped inventory`);
  }
  return record;
}

export function actionSetsForSlot(slot: GeneralSlot): readonly string[] {
  return ROLE_INVENTORY.filter((item) => item.classification === slot).map(
    (item) => item.role,
  );
}

export function advancedActionSets(): readonly string[] {
  return ROLE_INVENTORY.map((item) => item.role);
}

export function extraActionSets(): readonly string[] {
  return ROLE_INVENTORY.filter((item) => item.classification === "extra").map(
    (item) => item.role,
  );
}
