class Metrics:

    def __init__(self, standPositions):

        # --- contatori ---
        self.nUsers = 0          # clienti generati
        self.nRide = 0           # corse completate (arrivi a destinazione)
        self.nUserInLoco = 0     # clienti in loco partiti dallo stand
        self.nUserOnLine = 0     # clienti online raggiunti dal taxi

        # --- accumulatori di tempo ---
        self.waitedInLocoAcc = 0
        self.waitedOnLineAcc = 0
        self.rideTimeAcc = 0          # taxi con cliente a bordo
        self.timeBackToStandAcc = 0   # taxi vuoto verso uno stand
        self.timeToUserAcc = 0        # taxi vuoto verso un cliente

        # --- integrali nel tempo (aggiornati da update) ---
        self.lastTime = 0
        self.onLineQueueAcc = 0
        self.standPositions = list(standPositions)
        self.idleTaxiAccPerStand = {pos: 0 for pos in self.standPositions}
        self.queueAccPerStand = {pos: 0 for pos in self.standPositions}
        self.maxQueuePerStand = {pos: 0 for pos in self.standPositions}

        # --- clienti in loco per stand ---
        self.nUserInLocoPerStand = {pos: 0 for pos in self.standPositions}
        self.waitedInLocoAccPerStand = {pos: 0 for pos in self.standPositions}


    # ------------------------------------------------------------------
    # Da chiamare a ogni evento, PRIMA di processarlo
    # ------------------------------------------------------------------
    def update(self, time: int, taxiStands) -> None:
        dt = time - self.lastTime

        for pos in self.standPositions:
            stand = taxiStands.stands[pos]
            qLen = len(stand.userQueue)

            self.idleTaxiAccPerStand[pos] += stand.nTaxi * dt
            self.queueAccPerStand[pos] += qLen * dt
            if qLen > self.maxQueuePerStand[pos]:
                self.maxQueuePerStand[pos] = qLen

        self.onLineQueueAcc += len(taxiStands.onlineQueue) * dt
        self.lastTime = time


    # ------------------------------------------------------------------
    # Contatori e tempi
    # ------------------------------------------------------------------
    def incrementUserCounter(self) -> None:
        self.nUsers += 1


    def incrementRideCounter(self) -> None:
        self.nRide += 1


    def recordInLocoWait(self, standLocation: tuple[int, int], waitedTime: int) -> None:
        # quando un cliente in loco parte dallo stand
        self.nUserInLoco += 1
        self.waitedInLocoAcc += waitedTime
        self.nUserInLocoPerStand[standLocation] += 1
        self.waitedInLocoAccPerStand[standLocation] += waitedTime


    def recordOnLineWait(self, waitedTime: int) -> None:
        # quando il taxi raggiunge un cliente online
        self.nUserOnLine += 1
        self.waitedOnLineAcc += waitedTime


    def incrementRideTimeAcc(self, rideTime: int) -> None:
        self.rideTimeAcc += rideTime


    def incrementTimeBackToStand(self, time: int) -> None:
        self.timeBackToStandAcc += time


    def incrementTimeToUser(self, time: int) -> None:
        self.timeToUserAcc += time


    # ------------------------------------------------------------------
    # Risultati finali
    # ------------------------------------------------------------------
    def globalReport(self, endTime: int, nTaxi: int) -> dict:
        idleAcc = sum(self.idleTaxiAccPerStand.values())
        totalTaxiTime = endTime * nTaxi

        return {
            "nUsers": self.nUsers,
            "nRide": self.nRide,
            "avgWaitInLoco": self.waitedInLocoAcc / self.nUserInLoco if self.nUserInLoco > 0 else 0.0,
            "avgWaitOnLine": self.waitedOnLineAcc / self.nUserOnLine if self.nUserOnLine > 0 else 0.0,
            "avgQueueInLoco": sum(self.queueAccPerStand.values()) / endTime,
            "avgQueueOnLine": self.onLineQueueAcc / endTime,
            # frazione del tempo dei taxi in ciascuno stato (somma ~ 1)
            "fracRide": self.rideTimeAcc / totalTaxiTime,
            "fracToUser": self.timeToUserAcc / totalTaxiTime,
            "fracBackToStand": self.timeBackToStandAcc / totalTaxiTime,
            "fracIdle": idleAcc / totalTaxiTime,
        }


    def standReport(self, endTime: int) -> dict:
        report = {}
        for pos in self.standPositions:
            n = self.nUserInLocoPerStand[pos]
            report[pos] = {
                "avgIdleTaxi": self.idleTaxiAccPerStand[pos] / endTime,
                "avgQueue": self.queueAccPerStand[pos] / endTime,
                "maxQueue": self.maxQueuePerStand[pos],
                "nUserInLoco": n,
                "avgWaitInLoco": self.waitedInLocoAccPerStand[pos] / n if n > 0 else 0.0,
            }
        return report