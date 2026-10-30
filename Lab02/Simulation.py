from TaxiStand import TaxiStands
from User import User
from FutureEventSet import FutureEventSet, Event
from helpers import *

"""
    TO-DO:          
        - aggiungere le statistiche, probabilemte con una classe metrics fatta di contatori o robe del genere

"""

print("PORCO DIO COUNT: 13")



# Parameteres for taxi and taxi stands: 
N_STAND = 2
N_TAXI = 3
CAPACITY = [1, 2]
POLICY = "uniform"

# Parameters for Users:
REACH_PROB = 0.5

# Parameters for the simulation:
MAX_TIME = 100


standsCoord: list[tuple[int, int]] = []
for i in range(N_STAND):
    standsCoord.append(getNewLocation())
    
taxiStands = TaxiStands(CAPACITY, standsCoord)
taxiStands.distributeTaxi(N_TAXI, policy=POLICY)

FES = FutureEventSet()
time = 0

# Simulation Initialization:

spawnTime = time
        
spawnLocation = getNewLocation()
destination = getNewLocation()
while manhattanDistance(spawnLocation, destination) < 10: 
    spawnLocation = getNewLocation()
    destination = getNewLocation()
    
inLoco = True if coinToss(REACH_PROB) > REACH_PROB else False
newUser = User(spawnTime, spawnLocation, destination, inLoco)
newEvent = Event("CLIENT_SPAWN", spawnTime, spawnLocation, newUser)
FES.insertEvent(newEvent)

def log_state(time, FES, taxiStands, eventType, filename="simulation_log.txt"):
    """Aggiunge al file lo stato corrente della simulazione."""
    with open(filename, "a", encoding="utf-8") as f:
        print(file=f)
        print("=" * 20, file=f)
        print(file=f)
        print(f"Time: {time}", file=f)
        print(f"FES:\n{FES}", file=f)
        print(file=f)
        print(f"taxiStands:\n{taxiStands}", file=f)
        print(file=f)
        print(f"CurrentEvent: {eventType}", file=f)


while True:
    
    currentEvent = FES.getEvent()
    time = currentEvent.getTime()
    eventType = currentEvent.getType()
    
    log_state(time, FES, taxiStands, eventType, r"C:\Users\Gabriele\Desktop\Poli\Magistrale\Computer_aided_simulation_lab\Lab02\logFile.txt")
    
    if time > MAX_TIME: break
    
    if eventType == "CLIENT_SPAWN":
        
        # schedule next client spawn event
        newSpawnTime = time + getNewSpawnTime()
        
        newSpawnLocation = getNewLocation()
        newDestination = getNewLocation()
        while manhattanDistance(newSpawnLocation, newDestination) < 10: 
            newSpawnLocation = getNewLocation()
            newDestination = getNewLocation()
            
        newInLoco = coinToss(REACH_PROB)
        
        newUser = User(newSpawnTime, newSpawnLocation, newDestination, newInLoco)
        newEvent = Event("CLIENT_SPAWN", newSpawnTime, newSpawnLocation, newUser)
        FES.insertEvent(newEvent)
        
        # Compute user action
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
            raise ValueError("User is not definied for CLIENT_SPAWN type event")
        
        if currentUser.getInLocoFlag():
            nearestStandLocation = taxiStands.walkToStand(currentUser.getSPawnLocation())
            timeToStand = getTimeByFoot(currentUser.getSPawnLocation(), nearestStandLocation)
            arrivalTime = time + timeToStand
            currentUser.setNextLocation(nearestStandLocation)
            currentUser.setArrivalToStandTime(arrivalTime)
            arrivalToStand = Event("USER_ARRIVAL_TO_STAND", arrivalTime, nearestStandLocation, currentUser)
            FES.insertEvent(arrivalToStand)
        
        else:
            if taxiStands.existsIdleTaxi():
                standLocation = taxiStands.taxiCall(currentUser.getSPawnLocation())
                timeToUser = getTimeByTaxi(standLocation, currentUser.getSPawnLocation())
                arrivalTime = time + timeToUser
                taxiStands.taxiDeparture(standLocation)
                currentUser.setNextLocation(currentUser.getSPawnLocation())
                arrivalTouser = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, currentUser.getSPawnLocation(), currentUser)
                FES.insertEvent(arrivalTouser)
                
            else:
                taxiStands.insertUserOnLine(currentUser)
                
    elif eventType == "USER_ARRIVAL_TO_STAND":
        currentUser = currentEvent.getUser()
        if currentUser is None:
                    raise ValueError("User is not definied for USER_ARRIVAL_TO_STAND type event")
                
        standLocation = currentEvent.getLocation()
        
        if taxiStands.isIdle(standLocation):
            timeToDestination = getTimeByTaxi(standLocation, currentUser.getDestination())
            arrivalTime = time + timeToDestination
            
            taxiStands.taxiDeparture(standLocation)
            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
            FES.insertEvent(nextEvent)
        else:
            taxiStands.insertUserInLoco(standLocation, currentUser)
            
    elif eventType == "TAXI_ARRIVAL_TO_USER":
        currentUser = currentEvent.getUser()
        if currentUser is None:
            raise ValueError("User is not definied for USER_ARRIVAL_TO_STAND type event")
        
        timeToDestination = getTimeByTaxi(currentEvent.getLocation(), currentUser.getDestination())
        arrivalTime = time + timeToDestination
        
        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
        FES.insertEvent(nextEvent)
        
    elif eventType == "ARRIVAL_TO_DESTINATION":
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
                    raise ValueError("User is not definied for ARRIVAL_TO_DESTINATION type event")
                
        if taxiStands.hasUserOnLine():
            nextUser = taxiStands.getOnLineUser()
            timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSPawnLocation())
            arrivalTime = time + timeToUser
            
            nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, nextUser.getSPawnLocation(), nextUser)
            FES.insertEvent(nextEvent)
            
        else:
            nearestTaxiStand = taxiStands.findFreeStand(currentEvent.getLocation())
            timeToStand = getTimeByTaxi(currentEvent.getLocation(), nearestTaxiStand)
            arrivalTime = time + timeToStand
            
            nextEvent = Event("TAXI_ARRIVAL_TO_STAND", arrivalTime, nearestTaxiStand, None)
            FES.insertEvent(nextEvent)
            
    elif eventType == "TAXI_ARRIVAL_TO_STAND":
        
        standLocation = currentEvent.getLocation()
        
        if taxiStands.hasWaitingUser(currentEvent.getLocation()):
            
            nextUser, inLocoFlag = taxiStands.getUser(standLocation)
            
            if inLocoFlag:
                destination = nextUser.getDestination()
                timeToDestination = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToDestination
                
                nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, destination, nextUser)
                FES.insertEvent(nextEvent)
                
            else:
                destination = nextUser.getSPawnLocation()
                timeToUser = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToUser
                
                nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, destination, nextUser) 
                FES.insertEvent(nextEvent)  
                
        elif taxiStands.hasFreeSpace(standLocation):
            taxiStands.taxiArrival(standLocation)
            
        else:
            nextStandLocation = taxiStands.findFreeStand(standLocation)
            timeToStand = getTimeByTaxi(standLocation, nextStandLocation)
            arrivalTime = time + timeToStand
            
            nextEvent = Event("TAXI_ARRIVAL_TO_STAND", arrivalTime, nextStandLocation, None)      
            FES.insertEvent(nextEvent)  
            
    else:
        raise ValueError(f"Evento non gestito: {eventType}")
            
        
                
        
        