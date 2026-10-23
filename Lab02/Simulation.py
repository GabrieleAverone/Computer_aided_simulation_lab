from TaxiStand import TaxiStand, TaxiStands
from User import User
from FutureEventSet import FutureEventSet, Event
from helpers import *

"""
    TO-DO:
        - sistemare la funzione per cercare un taxStand quando un taxi lascia lo user, bisogna fre il check che lo stand
            sia libero
        - cambiare o capire come sistemare sta roba: se event = "TAXI ARRIVAL TO STAND" non ho modo di capire a quale
            stand sono arrivato e non posso verificare se ci sono posti liberi oppure no:
                - cambio la classe event e ci metto anche un campo destination, così posso anche 
                    alleggerire la classe user in teoria
                - provo a predirre in qualche modo quanti posti liberi ci saranno nello stand all'arrivo del taxi e tolgo 
                    l'evento dalla FES in qualche modo
                - faccio un sistema di prenotazioni in cui se un taxi decide di andare a quello stand è già considerato
                    prenotato dagli altri taxi --> poco realistico
                    
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
        newEvent = Event("CLIENT_SPAWN", spawnTime, newUser)
        
        # Compute user action
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
            raise ValueError("User is not definied for CLIENT_SPAWN type event")
        
        if currentUser.getInLocoFlag():
            nearestStandLocation = taxiStands.findNearestTaxiStand(currentUser.getSPawnLocation())
            timeToStand = getTimeByFoot(spawnLocation, nearestStandLocation)
            arrivalTime = time + timeToStand
            currentUser.setNextLocation(nearestStandLocation)
            
            arrivalToStand = Event("USER_ARRIVAL_TO_STAND", arrivalTime, currentUser)
            FES.insertEvent(arrivalToStand)
        
        else:
            if taxiStands.existsIdleTaxi():
                standLocation = taxiStands.taxiCall(spawnLocation)
                timeToUser = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToUser
                
                currentUser.setNextLocation(currentUser.getSPawnLocation())
                arrivalTouser = Event("ARRIVAL_TO_USER", arrivalTime, currentUser)
                
            else:
                taxiStands.insertUserOnLine(currentUser)
                
    elif eventType == "USER_ARRIVAL_TO_STAND":
        currentUser = currentEvent.getUser()
        if currentUser is None:
                    raise ValueError("User is not definied for USER_ARRIVAL_TO_STAND type event")
        standLocation = currentUser.getNextLocation()
        currentStand = taxiStands.getStandID(standLocation)
        
        if taxiStands.isIdle(currentStand):
            timeToDestination = getTimeByTaxi(standLocation, currentUser.getDestination())
            arrivalTime = time + timeToDestination
            
            currentUser.setNextLocation(standLocation)
            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser)
        else:
            taxiStands.insertUserInLoco(currentStand, currentUser)
            
    elif eventType == "TAXI_ARRIVAL_TO_USER":
        currentUser = currentEvent.getUser()
        if currentUser is None:
            raise ValueError("User is not definied for USER_ARRIVAL_TO_STAND type event")
        
        timeToDestination = getTimeByTaxi(currentUser.getNextLocation(), currentUser.getDestination())
        arrivalTime = time + timeToDestination
        
        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser)
    
    elif eventType == "TAKE_PASSENGER":
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
            raise ValueError("User is not definied for USER_ARRIVAL_TO_STAND type event")
        
        timeToDestination = getTimeByTaxi(currentUser.getNextLocation(), currentUser.getDestination())
        arrivalTime = time + timeToDestination
        
        currentUser.setNextLocation(currentUser.getDestination())
        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser)
        
    elif eventType == "ARRIVAL_TO_DESTINATION":
        currentUser = currentEvent.getUser()
        
        if currentUser is None:
                    raise ValueError("User is not definied for ARRIVAL_TO_DESTINATION type event")
                
        if taxiStands.hasUserOnLine():
            nextUser = taxiStands.getOnLineUser()
            timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSPawnLocation())
            arrivalTime = time + timeToUser
            
            nextUser.setNextLocation(nextUser.getSPawnLocation())
            nextEvent = Event("TAXI_ARRIVA_TO_USER", arrivalTime, nextUser)
            
        else:
            raise NotImplementedError
            
            
        
        
        
        
        
        
        
        
        
        
        
        
        
    elif eventType == "TAXI_ARRIVAL_TO_STAND":
        
        pass
                
                
        
                
        
        