import logging

import torch

from modeling import Imager, InitialBeam, QuadScanTransport
from torch.utils.data import DataLoader, Dataset, random_split
from tqdm import trange

logging.basicConfig(level=logging.INFO)
from image_processing import import_images

location = (
    "D:\\AWA\\phase_space_tomography_07_07_22" "\\Quadscan_data_matching_solenoid_180A"
)
base_fname = location + "\\DQ7_scan1_"

# process_images(base_fname, 10)

all_k, all_images, all_charges, xx = import_images()
all_charges = torch.tensor(all_charges)
all_images = torch.tensor(all_images)
all_k = torch.tensor(all_k)

all_k = all_k.cuda()
all_images = all_images.cuda()

print(all_images.shape)


# create data loader
class ImageDataset(Dataset):
    def __init__(self, k, images):
        self.images = images
        self.k = k

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        return self.k[idx], self.images[idx]


class QuadScanModel(torch.nn.Module):
    def __init__(self, initial_beam, transport, imager):
        super(QuadScanModel, self).__init__()
        self.beam_generator = initial_beam
        self.lattice = transport
        self.imager = imager

    def forward(self, K):
        initial_beam = self.beam_generator()
        output_beam = self.lattice(initial_beam, K)
        output_coords = torch.cat(
            [output_beam.x.unsqueeze(0), output_beam.y.unsqueeze(0)]
        )
        output_images = self.imager(output_coords)
        return output_images


train_dset, test_dset = random_split(ImageDataset(all_k, all_images), [17, 4])

train_dataloader = DataLoader(train_dset, batch_size=10)
test_dataloader = DataLoader(test_dset)

# define model components and model
bins = xx[0].T[0]
bandwidth = torch.tensor(1.0e-4)

defaults = {
    "s": torch.tensor(0.0).float(),
    "p0c": torch.tensor(65.0e6).float(),
    "mc2": torch.tensor(0.511e6).float(),
}

model = QuadScanModel(
    InitialBeam(1000, **defaults), QuadScanTransport(), Imager(bins, bandwidth)
)
model.cuda()
loss_function = torch.nn.MSELoss(reduction="sum")

if 1:
    # try simple training
    max_epochs = 100
    optim = torch.optim.Adam(model.parameters(), lr=0.001)
    #losses = []
    for epoch in trange(max_epochs):
        torch.cuda.nvtx.range_push("epoch")
        with torch.autograd.profiler.emit_nvtx():
            for _ in range(len(train_dataloader)):
                optim.zero_grad()
                torch.cuda.nvtx.range_push("step")
                torch.cuda.nvtx.range_push("data")
                local_k, local_im = next(iter(train_dataloader))
                torch.cuda.nvtx.range_pop()

                torch.cuda.nvtx.range_push("track")
                output_im = model(local_k)
                torch.cuda.nvtx.range_pop()

                loss = loss_function(output_im, local_im)
                torch.cuda.nvtx.range_push("backprop")
                loss.backward()
                torch.cuda.nvtx.range_pop()

                torch.cuda.nvtx.range_push("optim.step")
                optim.step()
                torch.cuda.nvtx.range_pop()

                torch.cuda.synchronize()
                torch.cuda.nvtx.range_pop()

                #print(loss)
                #losses += [loss.clone().cpu().detach()]

        torch.cuda.synchronize()
        torch.cuda.nvtx.range_pop()

    #fig, ax = plt.subplots()
    #ax.semilogy(losses)

    torch.save(model.state_dict(), "checkpoint.pt")

model.load_state_dict(torch.load("checkpoint.pt"))
model.cpu()

#dist = torch.distributions.MultivariateNormal(torch.zeros(6), torch.eye(6))
#base_distribution_samples = dist.sample([100000])

# plot results
#model.beam_generator.base_distribution_samples = base_distribution_samples
#predicted_images = model(all_k[:5, :1])

#compare_images(xx, predicted_images[:5, 0], all_images[:5, 0])


#plt.show()
