from TaxiStand import TaxiStands
from User import User
from FutureEventSet import FutureEventSet, Event
from helpers import *

"""
    TO-DO:          
        - aggiungere le statistiche, probabilemte con una classe metrics fatta di contatori o robe del genere

"""



# Parameteres for taxi and taxi stands: 
N_STAND = 5
N_TAXI = 5
CAPACITY = [1, 1, 1, 1, 1]
POLICY = "uniform"

# Parameters for Users:
REACH_PROB = 0.5


standsCoord: list[tuple[int, int]] = []
for i in range(N_STAND):
    standsCoord.append(getNewLocation())
    
taxiStands = TaxiStands(CAPACITY, standsCoord)
taxiStands.distributeTaxi(N_TAXI, policy=POLICY)

FES = FutureEventSet()
time = 0

def simInitialization():
    pass

while True:
    
    currentEvent = FES.getEvent()
    time += currentEvent.getTime()
    eventType = currentEvent.getType()
    
    if eventType == "CLIENT_SPAWN":
        
        # schedule next client spawn event
        spawnTime = time + getNewSpawnTime()
        spawnLocation = getNewLocation()
        destination = getNewLocation()
        inLoco = True if coinToss() > REACH_PROB else False
        
        newUser = User(spawnTime, spawnLocation, destination, inLoco)
        newEvent = Event("CLIENT_SPAWN", spawnTime, spawnLocation, newUser)
        
        # Compute user action
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
            raise ValueError("User is not definied for CLIENT_SPAWN type event")
        
        if currentUser.getInLocoFlag():
            nearestStandLocation = taxiStands.findNearestTaxiStand(currentUser.getSPawnLocation())
            timeToStand = getTimeByFoot(spawnLocation, nearestStandLocation)
            arrivalTime = time + timeToStand
            currentUser.setNextLocation(nearestStandLocation)
            
            arrivalToStand = Event("USER_ARRIVAL_TO_STAND", arrivalTime, nearestStandLocation, currentUser)
            FES.insertEvent(arrivalToStand)
        
        else:
            if taxiStands.existsIdleTaxi():
                standLocation = taxiStands.taxiCall(spawnLocation)
                timeToUser = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToUser
                
                currentUser.setNextLocation(currentUser.getSPawnLocation())
                arrivalTouser = Event("ARRIVAL_TO_USER", arrivalTime, currentUser.getSPawnLocation(), currentUser)
                
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
            
            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
        else:
            taxiStands.insertUserInLoco(standLocation, currentUser)
            
    elif eventType == "TAXI_ARRIVAL_TO_USER":
        currentUser = currentEvent.getUser()
        if currentUser is None:
            raise ValueError("User is not definied for USER_ARRIVAL_TO_STAND type event")
        
        timeToDestination = getTimeByTaxi(currentEvent.getLocation(), currentUser.getDestination())
        arrivalTime = time + timeToDestination
        
        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
        
    elif eventType == "ARRIVAL_TO_DESTINATION":
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
                    raise ValueError("User is not definied for ARRIVAL_TO_DESTINATION type event")
                
        if taxiStands.hasUserOnLine():
            nextUser = taxiStands.getOnLineUser()
            timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSPawnLocation())
            arrivalTime = time + timeToUser
            
            nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, nextUser.getDestination(), nextUser)
            
        else:
            nearestTaxiStand = taxiStands.findNearestTaxiStand(currentEvent.getLocation())
            timeToStand = getTimeByTaxi(currentEvent.getLocation(), nearestTaxiStand)
            arrivalTime = time + timeToStand
            
            nextEvent = Event("TAXI_ARRIVAL_TO_STAND", arrivalTime, nearestTaxiStand, None)
            
    elif eventType == "TAXI_ARRIVAL_TO_STAND":
        
        standLocation = currentEvent.getLocation()
        
        if taxiStands.hasWaitingUser(currentEvent.getLocation()):
            
            nextUser, inLocoFlag = taxiStands.getUser(standLocation)
            
            if inLocoFlag:
                destination = nextUser.getDestination()
                timeToDestination = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToDestination
                
                nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, destination, nextUser)
                
            else:
                destination = nextUser.getSPawnLocation()
                timeToUser = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToUser
                
                nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, destination, nextUser)   
                
        elif taxiStands.hasFreeSpace(standLocation):
            taxiStands.taxiArrival(standLocation)
            
        else:
            nextStandLocation = taxiStands.findNearestTaxiStand(standLocation)
            timeToStand = getTimeByTaxi(standLocation, nextStandLocation)
            arrivalTime = time + timeToStand
            
            nextEvent = Event("TAXI_ARRIVAL_TO_STAND", arrivalTime, nextStandLocation, None)        
            
        
                
        
        