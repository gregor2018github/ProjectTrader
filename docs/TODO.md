# Project Trader TODOs

## High Priority
- [ ] interaction menu for buying / selling goods at the market booths
- [ ] interaction menu for buying trading licenses at the city hall
- [ ] create a first version of the town class (with population, balance, happiness per pop type, etc)
- [ ] enlarge the map size while keeping the current city structure(it is already getting too small)

## Medium Priority
- [ ] design water tiles (plan how to animate them before implementing static ones)
- [ ] integrate reputation system with different factions (church, city, guilds, population types, etc)
- [ ] rethink the market mechanics - supply and demand, city size influence, etc.
- [ ] numerate the assets with visible numbers on the tilesets so that you don't have to count them every time - especially for trees
- [ ] upgrade the charts about personal statistics (hoverinfo, double charts, more data, days vs weeks as x axis)
- [ ] create a system to interact with a building. There will be "door areas" and when these are touched, you can do things with the buildings (later enter, for now only menu)
- [ ] Trading at the market should only be available between 6am and 10pm
- [ ] other people must stand behind the market booths, create and add NPC sprites

## Planned Features
- [ ] have the bell at the church ringing when the map is open and the player is close to the church (midday and midnight for now)
- [ ] Negative balance handling (e.g., loans)
- [ ] Add sound effects for buying and selling goods at the market
- [ ] Add sound effects for birds chirping during the day and crickets at night
- [ ] Bank Menu 
- [ ] Market events
- [ ] give the player 8 instead of 4 movement directions (diagonals)
- [ ] Warehouse upgrades
- [ ] Price influenced by Supply and Demand
- [ ] add candles, salts and herbs as tradable goods
- [ ] contract candles
- [ ] contract salt
- [ ] contract herbs
- [ ] Integrate a system to swap between different maps (e.g., town, house, shop)
- [ ] Revisite the Depot detail view window and add more statistics and graphs as soon as more game depth is implemented

## Bug Fixes
- [ ] the depot view window can sometimes not be opened. it will open the map view instead when clicking the big button
- [ ] When moving to the sides, the window polygons at night flicker (they never start at a tile corner, that seems to cause flicker)
- [ ] On daily statistics the cost of living never gets shown as it gets deducted at the same point in time, when the day switches
- [ ] charts for meat and wine (redish colors) flicker in the speed level fast, not on the fastest mode though, something might overlap with the background

## Finished Features
- [x] Expenditure overview in the depot detail view
- [x] interaction menu for church donations at the church building
- [x] when clicking on a building you are close by, you can open an interaction menu
- [x] Create a market area on the tiled project, connect it to the python code, only on the market the player can trade
- [x] with new stone tiles create a market area
- [x] create market booths as asset sprites
- [x] place the market booths in the market area
- [x] rework the base tileset for the ground (make them all modular so they can overlap each other better)
- [x] bugfix: Some houses flickered badly when moving due to wrong positioned object pins in Tiled
- [x] contract linen, contract meat, contract pottery
- [x] contract beer, contract wood
- [x] contract wheat, contract fish, refined stone contract
- [x] contracts hides, iron, stone, wool, wine
- [x] when watching the dialogue demo, the time is being paused
- [x] when watching the contract demo, the time is being paused
- [x] bugfix: overlay of the contract_view to grey out the background was not big enough to cover the sidebar area
- [x] bugfix: When opening the dialogue demo, all the buttons in the background where still clickable
- [x] bugfix: When opening the menu at the top right, the module buttons below it where still clickable
- [x] Demo to sign a contract (from the menu button for now just to check the functionality)
- [x] Added custom mouse cursor
- [x] Added night light effects for the church
- [x] create special night light areas for big buildings as polygons and let them shine every night (city hall)
- [x] create a church building as asset sprite
- [x] place the church building in the town map
- [x] defined new market area in the town map (in front of the city hall)
- [x] Added the city hall building to the town map
- [x] created city hall building asset sprite
- [x] When earning or losing money, the top money display always stays green or red, it gets stuck until the next transaction
- [x] Fixed a bug where lights visibly reset at midnight - now it is at noon 12.00, where all lights are off anyway
- [x] When moving as the player from top towards bottom, the player sprite can get stuck in collision boxes and must go up again to get free
- [x] give light points proper candle light sources with glow effect in the code, also design a time schedule when lights are on/off
- [x] Add lights to the windows of the houses during night time (first as points in the tiled map)
- [x] day and night cycle with different lighting
- [x] for debugging... fix the overlays at the map view (bottom info has to be replaced by... fps counter; time)
- [x] time must past slower - add a minute system (which will not be visible in the UI, but used for internal calculations)
- [x] when going to map view, the time may only be normal speed or paused
- [x] make the complete window a bit higher, see if there are problems related to that
- [x] create proper standardized tree assets
- [x] add the trees as objects via tiled object layers (that it can also be designed where they look best)
- [x] make the collision box of the player ever smaller at the top
- [x] add collision margins (so that houses can have a bit more or less space around at the particular sides)
- [x] Fix the walkthrough of the second fence with an invisible collision box
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
- [x] Make all sounds evenly loud (old trader voice is too silent) 
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