/**
 * ModeLink / ModeNavLink — <Link> and <NavLink> whose `to` keeps the
 * current page's mode (mothershipForPath.inMode, via useModePath). For the
 * surfaces that live inside a research which may belong to another mode's
 * tree (/inv/<id>?m=reading).
 */
import { Link, NavLink, type LinkProps, type NavLinkProps } from "react-router-dom";

import { useModePath } from "./useModeNavigate";

export function ModeLink({ to, ...rest }: Omit<LinkProps, "to"> & { to: string }) {
  const modePath = useModePath();
  return <Link to={modePath(to)} {...rest} />;
}

export function ModeNavLink({ to, ...rest }: Omit<NavLinkProps, "to"> & { to: string }) {
  const modePath = useModePath();
  return <NavLink to={modePath(to)} {...rest} />;
}
