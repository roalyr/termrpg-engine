# World

## Decided

### The surface

- **A 6×6 plane of surface cells.** Each cell is a hand-written location, like every
  other room. Neighbouring cells connect through exits on their edges. No engine
  feature: content only. (A4.10, A4.11, A4.12)
- **The surface hub sits in the centre** and is where the player starts. The shuttle
  pad is in a cell next to it. Every other point of interest lies near the edges.
  (A4.9, A4.11)

### Places

| Place | Role | Reached by |
|---|---|---|
| Surface hub | Start, main hub | — |
| Shuttle pad | Launches to the station on a schedule | Next cell to the hub |
| Research outpost | Remote base | Across the surface |
| Mining base | Industrial base | A chain of underground tunnel rooms from the hub |
| Orbital station | Transition port, transient hub, trade | Shuttle, on a schedule |
| Abandoned facility | Point of interest: combat, materials, data | Across the surface, near an edge |
| Excavation site | Point of interest: the exotic material | Across the surface, near an edge |

Every base has a set of rooms. (A4.5, A4.6)

### The orbital station

- A **transition port** for destinations beyond this pack.
- A **transient hub for people**: some arrive to stay, some leave.
- **Trade in imported goods and technology**, including parts the player can use to
  expand their own workshop or room. (A4.7)

### Points of interest

- **The abandoned facility** (in 1.0): automated defences still running. Combat,
  materials to gather and data to collect.
- **The excavation site** (in 1.0): not abandoned; people work shifts there. A
  crater, field or maze-like hazard area with its own effects and restrictions. Its
  reward, the exotic material, is the key to progress after 1.0. (A4.8)

## Estimates

About 70 to 80 locations: 36 surface cells, 3 bases of about 5 rooms, about 4 tunnel
rooms, about 5 station rooms, and two points of interest of 6 to 8 rooms each.
Surface cells are quick to cross. To confirm in C.

## Open

1. The surface map: which cell holds what, with coordinates.
2. Room lists for each base, the station and both points of interest.
3. Which areas are hazardous, hostile or deadly: the danger ladder. (C4)
4. Which areas restock (wreck piles, enemies), if any. (C7)
5. Room grid sizes. (C8)
6. The shuttle schedule. (A4.6)
7. How "expanding your workshop or room" works. See engine-requirements.md. (A4.7)
8. Where the farthest point of interest is, and what makes it the farthest.
