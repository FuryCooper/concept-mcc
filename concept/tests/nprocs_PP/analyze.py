# This file has to be run in pure Python mode!

# Include the code directory in the searched paths
import sys, os
concept_dir = os.path.realpath(__file__)
this_dir = os.path.dirname(concept_dir)
while True:
    if concept_dir == '/':
        raise Exception('Cannot find the .paths file!')
    if '.paths' in os.listdir(os.path.dirname(concept_dir)):
        break
    concept_dir = os.path.dirname(concept_dir)
sys.path.append(concept_dir)

# Imports from the CONCEPT code
from commons import *
from IO import load
from graphics import animate

# Use a matplotlib backend that does not require a running X-server
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Determine the number of snapshots from the outputlist file
N_snapshots = np.loadtxt(this_dir + '/outputlist').size

# Read in data from the CONCEPT snapshots
particles = []
for i in range(N_snapshots):
    fname = 'snapshot_a={:.3f}'.format(np.loadtxt(this_dir + '/outputlist')[i])
    particles.append([load(this_dir + '/output_' + str(j) + '/' + fname, write_msg=False) for j in (1, 2, 4, 8)])

# Using the particle order of the 0'th snapshot as the standard, find the corresponding
# ID's in the snapshots and order these particles accoringly.
N = particles[0][0].N
D2 = zeros(N)
ID = zeros(N, dtype='int')
for i in range(N_snapshots):
    x = particles[i][0].posx
    y = particles[i][0].posy
    z = particles[i][0].posz
    for j in (1, 2, 3):
        x_procs = particles[i][j].posx
        y_procs = particles[i][j].posy
        z_procs = particles[i][j].posz
        for l in range(N):
            for k in range(N):
                dx = x[l] - x_procs[k]
                if dx > half_boxsize:
                    dx -= boxsize
                elif dx < -half_boxsize:
                    dx += boxsize
                dy = y[l] - y_procs[k]
                if dy > half_boxsize:
                    dy -= boxsize
                elif dy < -half_boxsize:
                    dy += boxsize
                dz = z[l] - z_procs[k]
                if dz > half_boxsize:
                    dz -= boxsize
                elif dz < -half_boxsize:
                    dz += boxsize
                D2[k] = dx**2 + dy**2 + dz**2
            ID[l] = np.argmin(D2)
        particles[i][j].posx = particles[i][j].posx[ID]
        particles[i][j].posy = particles[i][j].posy[ID]
        particles[i][j].posz = particles[i][j].posz[ID]
        particles[i][j].momx = particles[i][j].momx[ID]
        particles[i][j].momy = particles[i][j].momy[ID]
        particles[i][j].momz = particles[i][j].momz[ID]

# Compute distance between particles in the two snapshots
fig_file = this_dir + '/result.pdf'
x = [particles[-1][j].posx for j in range(4)]
y = [particles[-1][j].posx for j in range(4)]
z = [particles[-1][j].posx for j in range(4)]
dist = [sqrt(array([min([(x[0][i] - x[j][i] + xsgn*boxsize)**2 + (y[0][i] - y[j][i] + ysgn*boxsize)**2 + (z[0][i] - z[j][i] + zsgn*boxsize)**2 for xsgn in (-1, 0, +1) for ysgn in (-1, 0, 1) for zsgn in (-1, 0, 1)]) for i in range(N)])) for j in range(4)]

# Plot
fig, ax = plt.subplots(3, sharex=True, sharey=True)
for i, a, d in zip((2, 4, 8), ax, dist[1:]):
    a.plot(d/boxsize, 'sr')
    a.set_ylabel('$|\mathbf{x}_{' + str(i) + '} - \mathbf{x}_1|/\mathrm{boxsize}$')
ax[-1].set_xlabel('Particle number')
plt.xlim(0, N - 1)
plt.ylim(0, 1)
fig.subplots_adjust(hspace=0)
plt.setp([ax.get_xticklabels() for ax in fig.axes[:-1]], visible=False)
plt.savefig(fig_file)

# Compare the different runs
tol = 1e-6
if any(np.mean(dist[j]/boxsize) > tol for j in range(4)):
    print('\033[1m\033[91m' + 'Runs with different numbers of processes yield different results!\n'
          + 'See ' + fig_file + ' for a visualization.' + '\033[0m')
    sys.exit(1)