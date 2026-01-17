# Project Trader TODOs

## High Priority

- [ ] make the collision box of the player ever smaller at the top
- [ ] add collision margins (so that houses can have a bit more or less space around at the particular sides)
- [ ] Fix the walkthrough of the second fence with an invisible collision box
- [ ]create proper standardized tree assets
- [ ] add the trees as objects via tiled object layers (that it can also be designed where they look best)
- [ ] make the complete window a bit higher, see if there are problems related to that

## Medium Priority

- [ ] Market events
- [ ] when going to map view, the time may only be normal speed or paused
- [ ] Add sound effects for buying and selling goods at the market
- [ ] upgrade the charts about personal statistics (hoverinfo, double charts, more data, days vs weeks as x axis)

## Planned Features
- [ ] Expenditure overview in the depot detail view
- [ ] Negative balance handling (e.g., loans)
- [ ] Bank Menu 
- [ ] give the player 8 instead of 4 movement directions (diagonals)
- [ ] Warehouse upgrades
- [ ] Price influenced by Supply and Demand
- [ ] Integrate a system to swap between different maps (e.g., town, house, shop)
- [ ] Revisite the Depot detail view window and add more statistics and graphs as soon as more game depth is implemented

## Bug Fixes
- [ ] On daily statistics the cost of living never gets shown as it gets deducted at the same point in time, when the day switches
- [ ] charts for meat and wine (redish colors) flicker in the speed level fast, not on the fastest mode though, something might overlap with the background
- [ ] Time progresses faster with higher frame rates, these two must be decoupled
- [ ] Make all sounds evenly loud (old trader voice is too silent)

Finished Features
- [x] Add all houses as proper objects via tiled object layers
- [x] Fix map view rendering artifacts (black lines between tiles at certain zoom levels)
- [x] Fix map view rendering artifacts when moving the player (tiles flicker at a certain line when moving)
- [x] Collisions with objects in the world must be improved (only tree demo so far)
- [x] Houses must actually overlap the player (like trees now do in the map demo) -> they must become ID'd objects rather than tiles
- [x] Fix how the depot_view looks like with the new screen size (free area on the right, overlapping bars, etc)
- [x] fix the map zoom (mousewheel is not working, + or - lets the game crash)
- [x] have a menu that shows graphs of how your personal statistics are developing (wealth, depot size, goods owned, etc)
- [x] Make the different menu elements like map, depot view and market truly modular that they can be added and removed at will at both sides
- [x] sound effects for walking
- [x] Add a free license on github 
- [x] Integrate the map system into the main game loop (link player position to map position)
- [x] Add a readme file to the project including gifs/screenshots
- [x] Add vertical bars to the chart which will indicate day changes
- [x] give x and y coordinates to the player instance
- [x] add docstrings
- [x] add type hints
- [x] Add a side menu panel with pictogram buttons
- [x] Shift menu button to the right (extension of the existing space)
- [x] Reorganize the top bar so that all products get separated by the money with a vertical stripe - only possible when Menu button goes to the right
- [x] Always start depot view with "Wealth Today" open. Also rename it as "Current Wealth"
- [x] Storage availability must become visible in the top menu bar
- [x] Player has only a limited amount of storage space
- [x] Transaction costs for buying and selling goods
- [x] Finish the depot view detail window