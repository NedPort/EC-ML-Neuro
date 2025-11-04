class myQueue:
    def __init__(self, capacity):
        # Maximum number of elements the queue can hold
        self.capacity = capacity
        # Array to store queue elements
        self.arr = [0] * capacity
        # Current number of elements in the queue
        self.size = 0

    # Check if queue is empty
    def isEmpty(self):
        return self.size == 0

    # Check if queue is full
    def isFull(self):
        return self.size == self.capacity

    # Enqueue
    def enqueue(self, x):
        if self.isFull():
            print("Queue is full!")
            return
        self.arr[self.size] = x
        self.size += 1

    # Dequeue
    def dequeue(self):
        if self.isEmpty():
            print("Queue is empty!")
            return
        for i in range(1, self.size):
            self.arr[i - 1] = self.arr[i]
        self.size -= 1

    # Get front element
    def getFront(self):
        if self.isEmpty():
            print("Queue is empty!")
            return -1
        return self.arr[0]

    # Get rear element
    def getRear(self):
        if self.isEmpty():
            print("Queue is empty!")
            return -1
        return self.arr[self.size - 1]


# Driver code
if __name__ == '__main__':
    q = myQueue(3)
    q.enqueue(10)
    q.enqueue(20)
    q.enqueue(30)
    print("Front:", q.getFront())
    q.dequeue()
    print("Front:", q.getFront())
    print("Rear:", q.getRear())
    q.enqueue(40)
    
