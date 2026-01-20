HERE EVERYTHING CAN GO - IMPLEMENTED IDEAS ARE DELETED FROM THIS FILE

- add market areas
    - these are on squares on the map
    - several market booths per market area
    - per good there will be one booth, player has to be near the booth to trade that good
    - only when in the vicinity of a market area the player can trade (otherwise market options are disabled/grayed out)

- Buildings
    - market booths
    - more houses
    - medium warehouse
    - large warehouse
    - church
    - guild hall
    - bank
    - bakery
    - blacksmith
    - mill
    - butcher
    - more regular houses

- Decoration Buildings
    - fountain
    - well
    - statues
    - park bench
    - crates and barrels
    - 

- when player gets new rights there will be a real medieval contract written out for them to sign... (really sign yourself with mouse)
    - scribble sound when they sign
    - different funny texts that change based on building or right or whatever

- trading licences 
    - player can only trade certain items after buying a licence from the guild
    - trading licences have a limited duration (like 1 month, 3 months, 6 months, 12 months)
    - can be linked to money, reputation, quests, completion of previous licences, etc.
    - prices for licenses can increase on a monthly basis (when the player also gets richer)

- have a market screamer/NPC that announces change

- carriage system 
    - player only has a limited amount of 100 storage units in carriage
    - he can only trade goods from the carriage if it is parked at a market area
    - player himself has place for 10 storage units (pockets)
    - extra tiny warehouse will be another 100 storage units
    - carriage speed is slower than walking, but on cobble stone it is nearly as fast as walking

- MAP FEATURES
    - we need cobblestone roads, squares
    - underground must be defined as gifs which will allow more modular overlapping of tiles (currently 'hard-drawn' between different tile types)
    - trees can grow in clusters of similar types (requires multiple tree sprites per type)
    - buildings can be entered (shop, house, warehouse, guild, etc)
    - inner views of buildings
    - NPSs for decoration (for now just standing around)
    - Animations
        - water that is actually moving
        - waving wheat fields
        - smoke from chimneys
        - bird flocks in highest zoom stage
        - animation for idle main character
    - Shadows
        - static for trees and buildings
        - traveling for NPCs and player
    - Sheeps that can stand on the meadow, eating and walking animations
    - a field of wheat that can be scaled as needed
    - at night time trading booths close and are covered with tarps

- have a pub where you can eat fancy food 
    - you might get temporary buffs (like better prices, more storage space, faster movement, etc)
    - menu will change daily with real medieval recipes
    - there are always three recipes available (cheap, medium, expensive)

- at the end of the year you will receive income tax and property tax statements that you have to pay
    - if you don't pay them on time you get fined or worse

- when opening a new menu page, there must be a rolling scroll effect
    - animation
    - sound effect

- add different chart types like candlestick charts

- hide random bottle messages in the world that give little stories or simply medieval sayings

- add the possibility to enter different order types (limit orders, stop orders, etc)

- Game must be savable and loadable
    - all game state must be serializable (player data, depot data, market data, city data, time data, etc)
    - implement save/load menu
    - autosave feature

- Main menu when starting the game
    - New Game
    - Load Game
    - Settings
    - Exit

- warehouses can be upgraded to hold more items

- a real city in the background
    - update statistics daily/weekly/monthly to not overload the system
    - the city must grow!

- dynamic economy based on supply and demand
    - base demand is determined by the population of the city
    - low prices increase demand, high prices decrease demand
    - long periods of high or low supply can influence base demand
    - fulfilling demand of the city properly leads to growth of the city (balance between )

- player can own houses where they live

- good deterioration 
    - bad warehouses will deteriorate and lose items over time
    - breakins can occur if the warehouse is not secure enough, player home can be the same

- building system - player can build houses, shops, warehouses, etc -> thus shape the town themselves
